## 后端入门part1 MySQL
# 01 终端截图
![alt text](<../images/屏幕截图 2026-10-12 181923.png>)
![alt text](<../images/屏幕截图 2026-10-12 182010.png>)
![alt text](<../images/屏幕截图 2026-10-12 182031.png>)
原代码见notes-FastAPI-1.py
1. MySQL模版
(1).新增（POST，CREATE）
sql = "INSERT INTO notes (title, content) VALUES (%s, %s)"
cursor.execute(sql, (title, content))
执行后用 cursor.lastrowid 获取新增 id
(2). 查询单条（GET，READ）
sql = "SELECT * FROM notes WHERE id=%s"
cursor.execute(sql, (note_id,))
cursor.fetchone()# fetchone() 取出查到的第一条结果
(3).查询全部笔记（列表接口）
SELECT * FROM notes;
搭配 cursor.fetchall()，返回多条数据
*代表取出全部字段；也可以写固定字段：SELECT id,title,content FROM notes WHERE id=%s
(4).查询全部
sql = "SELECT * FROM notes"
cursor.execute(sql)
(5).模糊查询（按标题搜索笔记，拓展）
SELECT * FROM notes WHERE title LIKE %s;
传参写法：("%" + keyword + "%",)，% 是通配符，匹配任意字符
(6).修改（PUT，UPDATE）
sql = "UPDATE notes SET title=%s, content=%s WHERE id=%s"
cursor.execute(sql, (title, content, note_id))
(7) .删除（DELETE）
sql = "DELETE FROM notes WHERE id=%s"
cursor.execute(sql, (note_id,))
WHERE不可去除，否则更新或删除时更新或删除所有内容
pymysql 驱动规定：SQL 语句里用%s作为参数占位符，之后把参数单独传给execute，而不是自己拼字符串
2. 请求方法 中文名称	对应操作	作用	        对应你笔记项目
    POST	新增	Create（增）	创建新数据	    add_note() 新增笔记，返回 note_id
    GET	    查询	Read（查）	    获取数据	    获取单条笔记 / 获取全部笔记
    PUT	    修改	Update（改）	更新整条数据	根据 note_id，完整替换一条笔记的标题 + 内容
    DELETE	删除	Delete（删）	删除数据	    根据 note_id 删除指定笔记
3. FastAPI 专用的抛出异常语法
 场景	                       代码	                                                            含义
资源不存在（GET/PUT/DELETE）	raise HTTPException(status_code=404, detail="笔记不存在")	      404
参数错误	                    raise HTTPException(status_code=400, detail="参数非法")	          400
服务器数据库异常	            raise HTTPException(status_code=500, detail="数据库错误")	       500
身份校验错误                    raise HTTPException(status_code=401, detail="未登录或token无效")   401
身份校验错误                    raise HTTPException(status_code=401, detail="账号或密码错误")      401
请求过多                        raise HTTPException(status_code=429, detail="请求繁忙，请重试")    429
服务器内部错误                  raise HTTPException(status_code=500, detail="消息发送失败")        500
4. 两种游标对比
① 默认游标（不带参数）
cursor = conn.cursor()
查询结果：元组，没有字段名
(1, "Linux笔记", "文件文件夹不能同名", datetime(...))
② DictCursor 字典游标
cursor = conn.cursor(pymysql.cursors.DictCursor)
查询结果：字典！
{"id":1, "title":"Linux笔记", "content":"文件文件夹不能同名", "create_time": datetime(...)}
5. cursor.execute(sql, 参数) 的规则：
第二个参数，永远需要传入一个容器：元组 tuple / 字典 dict，用来填充 SQL 里的%s占位符。
当只有 1 个参数：(note_id,)
(note_id) 只是括号包裹的数字，不是元组
(note_id,) 带逗号，才是单元素元组
多个参数：(title, content)，逗号分隔
# 02 用户注册与登录
1. 建表 SQL（在 MySQL 执行）
USE test_db;

-- 用户表 users
CREATE TABLE IF NOT EXISTS users(
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE, -- 账号，不能重复
    password VARCHAR(100) NOT NULL
);

-- 修改notes表，增加user_id，关联用户id
ALTER TABLE notes ADD COLUMN user_id INT NOT NULL;
逻辑：notes.user_id 对应 users.id，用来标记笔记是谁写的。
2. {} 在 Python 里，代表空字典。
3. 变量名后面写:类型，再写等号赋值。如def add_note(title: str, content: str, uid:int=Depends(get_current_user_id)):

# 03 存储笔记长文本、图片方案？
1. 图片存储
图片不要直接存入数据库，数据库只保存图片文件的访问 URL / 文件路径，把图片存入对象存储（OSS，如阿里云 OSS），或者本地文件服务器（磁盘文件夹）
2. 长文本存储
方案 A：文档数据库 MongoDB
MongoDB 是非关系型数据库，天然适合存储大段富文本、嵌套结构（笔记可以附带图片链接、标签、草稿版本），不需要固定表结构，适合笔记这类可变内容。
方案 B：对象存储 + MySQL 元信息
笔记正文文本也可以存到对象存储，MySQL 只保存笔记标题、作者 ID、创建时间、正文文件地址。
方案 C：Redis 做缓存加速
笔记经常被读取，可以把热门笔记缓存到 Redis，减少 MySQL 查询压力。