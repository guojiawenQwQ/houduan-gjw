#完成Part1 01
#原来版本1，原文件名notes-FastAPI.py
#保存，启动服务：python notes-FastAPI.py
#打开 http://127.0.0.1:8000/docs 测试
from fastapi import FastAPI, HTTPException# 从fastapi包导入两个工具：FastAPI用来创建web服务，HTTPException用来返回404这类错误信息
import pymysql

app = FastAPI(title="笔记接口")# title是接口文档页面显示的标题

# 数据库连接配置
def get_db_conn():# def数据库连接函数：调用这个函数，就能拿到MySQL的连接对象 # 连接mysql数据库(get database connection)
    conn = pymysql.connect(
        host="localhost",# 数据库在本机
        user="root",#登录账号，本地默认 root
        password="GJWgjw580098",
        database="test_db",
        charset="utf8mb4" )# 支持中文存储,防止中文乱码
    return conn # 返回数据库连接

# 1.新增笔记
@app.post("/note/add")# @app.post 定义POST接口，访问路径是 /note/add
def add_note(title: str, content: str): # 字符串类型
    conn = get_db_conn()# 获取数据库连接
    cursor = conn.cursor()# 创建游标，用来执行SQL语句
    sql = "INSERT INTO notes(title, content) VALUES(%s, %s)"# 执行SQL，把(title,content)填入上面两个%s位置,%s是占位符（pymysql专用）
    # pymysql 驱动规定：SQL 语句里用%s作为参数占位符，之后把参数单独传给execute，而不是自己拼字符串
    cursor.execute(sql, (title, content))
    conn.commit()# 提交事务！插入/修改/删除必须commit，数据才真正存入数据库
    new_id = cursor.lastrowid# 获取刚刚新增这条记录,拿到上一条 INSERT 插入语句，自动生成的自增主键 id
    cursor.close()
    conn.close()
    return {"msg": "新增成功", "note_id": new_id}
    #返回一个Python 字典，有两个 key：
    # msg：消息文本，告诉前端 / 调用者执行结果,msg 是 message 的简写，中文意思：提示信息、消息。
    # note_id：刚刚插入笔记的自增主键 id（就是前面 cursor.lastrowid拿到的值）

# 2.根据ID查询笔记
@app.get("/note/read/{note_id}")# GET接口，路径 /note/{note_id} ，note_id是路径参数
def get_note(note_id: int):
    conn = get_db_conn()
    cursor = conn.cursor(pymysql.cursors.DictCursor)# DictCursor：查询结果以字典形式返回（键是列名，方便看）
    cursor.execute("SELECT * FROM notes WHERE id=%s", (note_id,))
    row = cursor.fetchone()# fetchone() 取出查到的第一条结果
    cursor.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="笔记不存在")# raise 是抛出异常，FastAPI 框架捕获后，直接向前端返回标准 HTTP 错误响应
    return row

# 3.修改笔记
@app.put("/note/update/{note_id}")
def update_note(note_id: int, title: str, content: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    sql = "UPDATE notes SET title=%s, content=%s WHERE id=%s"
    cnt = cursor.execute(sql, (title, content, note_id))
    conn.commit()
    cursor.close()
    conn.close()
    if cnt == 0:
        raise HTTPException(status_code=404, detail="笔记不存在，修改失败")
    return {"msg":"修改成功"}

#4.删除笔记
@app.delete("/note/delete/{note_id}")
def del_note(note_id: int):
    conn = get_db_conn()
    cursor = conn.cursor()
    cnt = cursor.execute("DELETE FROM notes WHERE id=%s", (note_id,))
    conn.commit()
    cursor.close()
    conn.close()
    if cnt ==0:
        raise HTTPException(status_code=404, detail="笔记不存在，删除失败")
    return {"msg":"删除成功"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("notes-FastAPI:app", host="0.0.0.0", port=8000, reload=True)
