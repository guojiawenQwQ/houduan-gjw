#完成Part1 01+02 ,Part2 01+02
#原来版本3，原文件名notes-FastAPI.py
#保存，启动服务：python notes-FastAPI.py
#打开 http://127.0.0.1:8000/docs 测试

from fastapi import FastAPI, HTTPException, Depends
import pymysql
import uuid
import redis  # 导入redis库
import json   #导入 json 库，实现字典 ↔ json 字符串互相转换，用来存缓存，Redis只能存字符串，不能直接存 Python 字典，所以要用json库做转换

app = FastAPI(title="笔记CRUD")

# 连接Redis
redis_client = redis.Redis( # redis_client：我们自己取的变量名
    # redis.Redis()：库redis里提供的类（Class）Redis，用来创建 Redis 连接实例,括号里面写 Redis 服务的地址、端口、数据库编号等配置
    host="localhost",
    port=6379, # redis默认端口6379
    db=0, # 使用redis里编号0的数据库（redis可以分多个数据库隔离数据）,Redis 自带16 个逻辑数据库（0~15），互相隔离。默认用 db=0
    decode_responses=True  # 自动把redis返回的二进制bytes转成普通字符串，不用手动decode
)

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
    cursor.execute("INSERT INTO users(username,password) VALUES(%s,%s)",(username,password))
    conn.commit()
    cursor.close()
    conn.close()
    return {"msg":"注册成功"}

# 登录接口，成功返回token
@app.post("/user/login")
def login(username: str, password: str):
    conn = get_db_conn()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT id,username FROM users WHERE username=%s AND password=%s",(username,password))
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
    conn = get_db_conn()
    cursor = conn.cursor()
    sql = "INSERT INTO notes(title,content,user_id) VALUES(%s,%s,%s)"
    cursor.execute(sql, (title, content, uid))
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return {"msg": "新增成功", "note_id": new_id}

# 2.查询笔记
@app.get("/note/read/{note_id}")
def get_note(note_id: int):
    # 先查Redis缓存，key命名：note:笔记id
    cache_key = f"note:{note_id}"# 构造redis的key #f""：f-string，python 的字符串拼接语法，大括号{}里面放变量，会把变量的值塞到字符串里
    cache_data = redis_client.get(cache_key)# 去redis读取这个key对应的数据 #Redis 就是放 cache（缓存）的地方
    # 给每个笔记上一个锁
    lock_key = f"lock:note:{note_id}" 
    # 如果缓存中有笔记，直接返回缓存里的数据
    if cache_data:
        return json.loads(cache_data) # json.loads：把redis存的json字符串，转回python字典，直接返回
    # 尝试获取锁，nx:不存在才设置，ex:锁超时时间，防止死锁
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
    conn = get_db_conn()
    cursor = conn.cursor()
    # 额外判断：这条笔记user_id必须等于当前登录用户uid
    sql = "UPDATE notes SET title=%s, content=%s WHERE id=%s AND user_id=%s"
    cnt = cursor.execute(sql, (title, content, note_id, uid))
    conn.commit()
    cursor.close()
    conn.close()
    if cnt == 0:
        raise HTTPException(status_code=404, detail="笔记不存在或者不是你的笔记，修改失败")
    # 删除缓存
    cache_key = f"note:{note_id}"
    redis_client.delete(cache_key)
    return {"msg":"修改成功"}

#4.删除笔记：只能删除自己的笔记
@app.delete("/note/delete/{note_id}")
def del_note(note_id: int, uid:int=Depends(get_current_user_id)):
    conn = get_db_conn()
    cursor = conn.cursor()
    # 增加 user_id 判断，只能删自己的笔记
    cnt = cursor.execute("DELETE FROM notes WHERE id=%s AND user_id=%s", (note_id, uid))
    conn.commit()
    cursor.close()
    conn.close()
    if cnt ==0:
        raise HTTPException(status_code=404, detail="笔记不存在或者不是你的笔记，删除失败")
    # 删除缓存
    cache_key = f"note:{note_id}"
    redis_client.delete(cache_key)
    return {"msg":"删除成功"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("notes-FastAPI:app", host="0.0.0.0", port=8000, reload=True)
