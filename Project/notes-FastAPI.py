from fastapi import FastAPI, HTTPException, Depends
import pymysql
import uuid
import redis  
import json   
import pika#pika 是 Python 用来操作 RabbitMQ 的第三方库（客户端）
#import pika = 把这个库导入代码，这样你的 Python 程序就能连接、收发 RabbitMQ 消息队列。

app = FastAPI(title="笔记CRUD")

# 连接Redis
redis_client = redis.Redis(
    host="localhost",
    port=6379,
    db=0, 
    decode_responses=True  
)

# 连接RabbitMQ
def get_rabbitmq_conn():
    credentials = pika.PlainCredentials('admin', 'GJWgjw580098')
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host='localhost', credentials=credentials)
    )
    channel = connection.channel()
    # 声明队列，不存在自动创建
    channel.queue_declare(queue='note_task_queue', durable=True)
    return channel, connection

# 数据库连接
def get_db_conn():
    conn = pymysql.connect(
        host="localhost",
        user="root",
        password="GJWgjw580098",
        database="test_db",
        charset="utf8mb4"
    )
    return conn

# 简易token存储（内存，重启服务就清空，作业演示用）
token_to_uid = {}

# 注册接口
@app.post("/user/register")
def register(username: str, password: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    # 查询用户名是否已经存在
    cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
    row = cursor.fetchone()
    if row:
        raise HTTPException(status_code=400, detail="用户名已存在")
    # 插入新用户
    sql = "INSERT INTO users(username,password) VALUES(%s,%s)"
    cursor.execute(sql,(username,password))
    conn.commit()
    cursor.close()
    conn.close()
    return {"msg":"注册成功"}

# 登录接口，成功返回token
@app.post("/user/login")
def login(username: str, password: str):
    conn = get_db_conn()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    sql = "SELECT id,username FROM users WHERE username=%s AND password=%s"
    cursor.execute(sql,(username,password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    # 生成随机token
    token = str(uuid.uuid4())
    token_to_uid[token] = user["id"]
    return {"msg":"登录成功","token":token}

# 依赖函数：从token拿到当前登录用户id
def get_current_user_id(token: str):
    if token not in token_to_uid:
        raise HTTPException(status_code=401, detail="未登录或token无效")
    return token_to_uid[token]

# 1.新增笔记
@app.post("/note/add")
def add_note(title: str, content: str, uid:int=Depends(get_current_user_id)):
# 1.封装任务消息
    task = { # task_msg 是一个Python 字典，用来打包这次要交给消费者执行的任务信息
        "msg_id": str(uuid.uuid4()),
        "user_id": uid,
        "title": title,
        "content": content,
        "action": "add"
    }
    try:
        # 2.发送消息到MQ队列
        channel,conn = get_rabbitmq_conn()
        channel.basic_publish(
            exchange='', # 使用默认交换机，默认交换机是直连类型（direct），有一条固定规则：routing_key = 队列名，消息就直接送到这个队列。
            routing_key='note_task_queue',
            body=json.dumps(task),
            properties=pika.BasicProperties(delivery_mode=2) # 消息持久化
            )
        # 关闭连接
        conn.close()
    except Exception:
        raise HTTPException(status_code=500, detail="消息发送失败,请检查RabbitMQ服务")
    # 直接返回，不等待数据库插入！
    return {"msg": "任务已提交到MQ,后台异步保存笔记"}

# 2.查询笔记
@app.get("/note/read/{note_id}")
def get_note(note_id: int):
    cache_key = f"note:{note_id}"
    cache_data = redis_client.get(cache_key)
    # 给每个笔记上一个锁
    lock_key = f"lock:note:{note_id}" 
    # 如果缓存中有笔记，直接返回缓存里的数据
    if cache_data:
        return json.loads(cache_data) 
    lock_ok = redis_client.set(lock_key, "1", nx=True, ex=10)
    if not lock_ok:
        # 获取锁失败 → 直接返回，或者短暂重试
        raise HTTPException(status_code=429, detail="请求繁忙，请重试")
    
    try:
        # 获取锁成功，缓存不存在，查询MySQL
        conn = get_db_conn()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        sql = "SELECT id, title, content FROM notes WHERE id = %s"
        cursor.execute(sql, (note_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if not row:
            # 笔记不存在，缓存空数据，防止缓存穿透，设置缓存
            redis_client.setex(cache_key,3600, json.dumps({"msg":"笔记不存在"}))
            raise HTTPException(status_code=404, detail="笔记不存在或者不是你的笔记")
        # MySQL查到了，写入Redis缓存，设置过期时间
        redis_client.setex(
            cache_key,
            86400,  # 一天后自动过期
            json.dumps(row)
        )
        return row
    finally:
        # 无论成功失败，最后一定要释放锁！
        redis_client.delete(lock_key)

# 3.修改笔记：只能修改自己的笔记
@app.put("/note/update/{note_id}")
def update_note(note_id: int, title: str, content: str, uid:int=Depends(get_current_user_id)):
    task = {
        "msg_id": str(uuid.uuid4()),
        "action": "update",
        "note_id": note_id,
        "title": title,
        "content": content,
        "user_id": uid
    }
    try:
        channel, conn = get_rabbitmq_conn()
        channel.basic_publish(
        exchange="",
        routing_key="note_task_queue",
        body=json.dumps(task),
        properties=pika.BasicProperties(delivery_mode=2) # 消息持久化
        )
        conn.close()
    except Exception:
        raise HTTPException(status_code=500, detail="消息发送失败,请检查RabbitMQ服务")
    # 修改数据要删掉redis旧缓存，下次查询重新缓存
    cache_key = f"note:{note_id}"
    redis_client.delete(cache_key)
    return {"msg":"修改任务已提交到MQ,后台异步处理"}

#4.删除笔记：只能删除自己的笔记
@app.delete("/note/delete/{note_id}")
def del_note(note_id: int, uid:int=Depends(get_current_user_id)):
    task = {
        "msg_id": str(uuid.uuid4()),
        "action": "delete",
        "note_id": note_id,
        "user_id": uid
    }
    try:
        channel, conn = get_rabbitmq_conn()
        channel.basic_publish(
        exchange="",
        routing_key="note_task_queue",
        body=json.dumps(task),
        properties=pika.BasicProperties(delivery_mode=2)
        )
        conn.close()
    except Exception:
        raise HTTPException(status_code=500, detail="消息发送失败,请检查RabbitMQ服务")
    # 删除Redis缓存
    cache_key = f"note:{note_id}"
    redis_client.delete(cache_key)
    return {"msg":"删除任务已提交到MQ,后台异步处理"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("notes-FastAPI:app", host="0.0.0.0", port=8000, reload=True)
