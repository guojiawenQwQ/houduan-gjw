#完成Part1 01+02
#原来版本2，原文件名notes-FastAPI.py
#保存，启动服务：python notes-FastAPI.py
#打开 http://127.0.0.1:8000/docs 测试

from fastapi import FastAPI, HTTPException, Depends
#Depends = 依赖注入，FastAPI 里面专门用来抽取公共、重复的代码，把重复逻辑单独拿出来，不用每个接口都复制粘贴。
import pymysql
import uuid# 导入uuid，用来生成唯一随机字符串（token令牌），可以使不暴露用户信息，别人拿到 token 才能操作账号

app = FastAPI(title="带用户登录的笔记CRUD")

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

# 简易token存储（内存，重启服务就清空）
token_to_uid = {}# 全局字典，存放 token -> uid # {} 在 Python 里，代表空字典。

# 注册接口
@app.post("/user/register")
def register(username: str, password: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    # 查询用户名是否已经存在
    cursor.execute("SELECT id FROM users WHERE username=%s",(username,))
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
def login(username: str, password: str):# login为登录函数
    conn = get_db_conn()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT id,username FROM users WHERE username=%s AND password=%s",(username,password))
    # id：用户编号（数字，主键，唯一不变），username：用户名（账号，字符串，用来登录），数据库外键关联（笔记归属）时用数字 id 效率更高
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    # 生成随机token
    token = str(uuid.uuid4())# uuid.uuid4()：生成一串全球几乎不会重复的随机字符串对象 # str(...)：把它转成字符串，方便存字典、传给前端
    token_to_uid[token] = user["id"] # 登记：这张通行证属于用户id# 从 user 这个字典里，取出 key 为id的值，也就是用户的数字编号 uid。
    #用变量 token 当作 key，去访问字典变量 token_to_uid
    return {"msg":"登录成功","token":token}

# 依赖函数：从token拿到当前登录用户id
def get_current_user_id(token: str):
    if token not in token_to_uid:
        raise HTTPException(status_code=401, detail="未登录或token无效")
    return token_to_uid[token]

# 1.新增笔记：自动带上当前用户user_id
@app.post("/note/add")
def add_note(title: str, content: str, uid:int=Depends(get_current_user_id)):# Depends(...)：FastAPI 依赖注入，代表执行括号里面的函数
    conn = get_db_conn()
    cursor = conn.cursor()
    sql = "INSERT INTO notes(title,content,user_id) VALUES(%s,%s,%s)"
    cursor.execute(sql, (title, content, uid))
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return {"msg": "新增成功", "note_id": new_id}

# 2.查询笔记（可以继续看，不限制）
@app.get("/note/read/{note_id}")
def get_note(note_id: int):
    conn = get_db_conn()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT * FROM notes WHERE id=%s", note_id)
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return row

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
    return {"msg":"删除成功"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("notes-FastAPI:app", host="0.0.0.0", port=8000, reload=True)
