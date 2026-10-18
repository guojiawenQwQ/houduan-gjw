#完成入门和进阶Part1-Part4部分
#启动 RabbitMQ 服务:sudo service rabbitmq-server start
#python notes-FastAPI.py
#python zhixing.py
#访问 http://127.0.0.1:8000/docs

from fastapi import FastAPI, HTTPException, Depends
import pymysql
import uuid
import redis  
import json   
import pika
import requests # 导入requests库，用来发送http网络请求，访问MiMo远程API 
from fastapi.middleware.cors import CORSMiddleware #导入跨域中间件

app = FastAPI(title="笔记CRUD")

# 允许前端网页跨域访问后端接口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MiMo Responses API 配置 
AI_API_URL = "https://api.xiaomimimo.com/v1/responses"
MIMO_MODEL = "mimo-v2.5-pro"
MIMO_API_KEY = "sk-chptuboiuw6s9a1n7m6kext3ewsdpk5hk0an1e1w52boh8h1"
# 【内存存储会话】字典，key是session_id会话ID，value是该会话的聊天历史消息列表
session_store = {}

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

#工具查询函数
def query_note_by_id(note_id: int):
    cache_key = f"note:{note_id}"
    cache_data = redis_client.get(cache_key)
    # 给每个笔记上一个锁
    lock_key = f"lock:note:{note_id}" 
    # 如果缓存中有笔记，直接返回缓存里的数据
    if cache_data:
        return json.loads(cache_data) 
    lock_ok = redis_client.set(lock_key, "1", nx=True, ex=10)
    if not lock_ok:
        # 获取锁失败 → 返回提示文字，不抛HTTP异常
        return "请求繁忙，请重试"
    
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
            return "笔记不存在或者不是你的笔记"
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

#告诉大模型可以调用的工具
tools = [
    {
        "type": "function",# 固定值：代表这是一个函数工具
        "function": {
            "name": "query_note_by_id",# name：工具的名字！AI想调用工具时，就会返回这个名字，后端靠这个名字匹配执行哪个Python函数
            "description": "【重要：不要在回答里文字描述工具，必须直接调用这个函数！】根据笔记ID，查询笔记完整标题和正文内容。用户询问笔记内容时，使用该工具查询，不要编造笔记信息。",# description：描述这个工具能干什么。大模型会读这句话，判断用户问题要不要调用这个工具
            "parameters": { # parameters：定义这个函数需要哪些参数；object代表参数是一个对象（字典）
                "type": "object",
                "properties": { # properties：列出所有参数
                    "note_id": {
                        "type": "integer",# integer：参数类型是整数，笔记ID是数字
                        "description": "笔记的id编号"# 参数说明，告诉AI这个note_id是什么含义
                    }
                },
                "required": ["note_id"] # required：必填参数列表。意思：调用这个工具**必须提供note_id，不能缺少**
            }
        }
    }
]

# 1.新增笔记
@app.post("/note/add")
def add_note(title: str, content: str, uid:int=Depends(get_current_user_id)):
# 1.封装任务消息
    task = { 
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
            exchange='', 
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

# 按账号名或笔记标题找出笔记 id，正文仍走 /note/read/{note_id}
@app.get("/note/find")
def find_note_ids(keyword: str):
    conn = get_db_conn()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("SELECT id FROM users WHERE username=%s", (keyword,))
        user = cursor.fetchone()
        account_note_ids = []
        if user:
            cursor.execute("SELECT id FROM notes WHERE user_id=%s ORDER BY id", (user["id"],))
            account_note_ids = [row["id"] for row in cursor.fetchall()]
        cursor.execute("SELECT id FROM notes WHERE title=%s ORDER BY id", (keyword,))
        title_note_ids = [row["id"] for row in cursor.fetchall()]
        return {
            "keyword": keyword,
            "user_found": bool(user),
            "account_note_ids": account_note_ids,
            "title_note_ids": title_note_ids,
        }
    finally:
        cursor.close()
        conn.close()

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

def extract_reply_text(result):
    """从 Responses API 的 output 里取出给用户看的正文，跳过思考过程。"""
    texts = []
    fallback = []
    output_list = result.get("output") or []
    if output_list is None:
        output_list = []
    for item in output_list:
        # 如果当前项是工具调用，跳过文本提取
        if "tool_calls" in item:
            continue
        content = item.get("content")
        chunks = []
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, str):
                    chunks.append(block)
                elif isinstance(block, dict) and block.get("text"):
                    if block.get("type") == "reasoning_text":
                        fallback.append(block["text"])
                    else:
                        chunks.append(block["text"])
        if item.get("type") == "message" or item.get("role") == "assistant":
            texts.extend(chunks)
        else:
            fallback.extend(chunks)
    if texts:
        return "\n".join(texts)
    if fallback:
        return "\n".join(fallback)
    return ""

# 与AI聊天
@app.post("/chat")
def chat_with_ai(question: str,session_id: str):
    #构造请求头
    headers = {
        "api-key": MIMO_API_KEY, #鉴权
        "Content-Type": "application/json" # 告诉服务器：发送的数据是json格式
    }
    # 判断：如果这个session_id不存在于会话存储，就新建空聊天列表
    if session_id not in session_store:
        session_store[session_id] = [
            {
                "role": "system",
                "content": "你拥有query_note_by_id工具。当用户需要查询笔记信息时，**禁止用文字描述调用工具，必须输出tool_calls来调用函数**，不能自己编造笔记内容。拿到工具返回结果之后，再整理信息回复用户。"
            }
        ]
    # 把用户当前消息追加到这个会话的历史记录，role=user代表用户发言
    session_store[session_id].append({"role":"user", "content": question})
    #session_store[session_id],取出字典中 session_id 对应的聊天列表（list）,这个列表就是当前这一段对话的所有历史消息
    #.append(),列表自带方法：在列表末尾追加一条新元素（往聊天记录最后面新增一条消息）
    
    # 构造请求体
    # 把历史列表记录传给 MiMo
    question_text = {
        "model": MIMO_MODEL,
        "input": session_store[session_id],
        "tools": tools
    }
    #发送POST请求到MiMo服务器
    try:
        # 发送http请求，headers请求头，json自动序列化question_text
        response = requests.post(
            url=AI_API_URL, # 请求目标地址，就是MiMo的API地址
            headers=headers, # 把上面写好的请求头传过去
            json=question_text, # 自动把req_body字典转为json字符串作为请求体
            timeout=120 # 超时时间：120秒，如果120秒没响应直接报错
        )
        # 如果http报错（401/404/500）直接抛出异常
        response.raise_for_status()
        # 把返回的字符串转成python字典
        result = response.json()
        print("====MiMo原始返回====")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        # ==========【修改点1】遍历output，寻找function_calls ==========
        tool_calls = None
        model_msg = None
        for out_item in result.get("output", []):
            if out_item.get("type") == "function_call":
                tool_calls = out_item
                model_msg = out_item
                break

        
        # 判断：AI是否想要调用工具 tool_calls
        if tool_calls is not None:
            # 1.把AI发起工具调用这条消息存入会话上下文
            session_store[session_id].append(model_msg)
            # 取出工具调用信息，MiMo结构是 function_call
            func_name = model_msg["name"]#读取工具调用信息，拿到要执行的函数名字,这里拿到的就是 "query_note_by_id"
            func_args = json.loads(model_msg["arguments"])
            note_id = func_args["note_id"]
            # 执行我们的查询笔记工具函数
            if func_name == "query_note_by_id":
                tool_result = query_note_by_id(note_id)
            # 2.把工具返回结果，追加进会话历史
            session_store[session_id].append({
                "role": "tool",
                "tool_call_id": model_msg["call_id"],
                "content": json.dumps(tool_result, ensure_ascii=False)
            })
            # 二次请求：把更新后的会话再发给AI，让AI整理结果给用户
            question2 = {
                "model": MIMO_MODEL,
                "input": session_store[session_id],
                "tools": tools
            }
            response2 = requests.post(AI_API_URL, headers=headers, json=question2, timeout=120)
            response2.raise_for_status()
            result2 = response2.json()
            final_ai_msg = extract_reply_text(result2)
            #从 MiMo 返回的数据里，找到 output 数组的第一条内容，取出 content 里面 AI 回答的文本，保存到变量。

            # AI最终回答存入会话
            session_store[session_id].append({"role": "assistant", "content": final_ai_msg})
            return {"session_id": session_id, "ai_reply": final_ai_msg}

        #没有tool调用，普通对话，直接返回
        ai_text = extract_reply_text(result)
        
        # 将AI的回复也加入会话历史，下一轮提问时一起传给AI，实现记忆上下文
        session_store[session_id].append({"role":"assistant", "content": ai_text})
        return {
            "session_id":session_id,
            "user_input": question,
            "ai_reply": ai_text
        }
    except Exception as e:
        import traceback
        traceback.print_exc() # 打印完整错误堆栈，终端直接看到哪里崩了
        raise HTTPException(status_code=500, detail=f"调用MiMo失败:{str(e)}") #str(e)：把错误对象e转成字符串，拿到具体错误详情。

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("notes-FastAPI:app", host="0.0.0.0", port=8000, reload=True)
