import pymysql

# 建立数据库连接
conn = pymysql.connect(
    host="localhost",
    user="pyuser",
    password="GJWgjw580098",
    database="mysql"
)
print("✅ MySQL连接成功！")

# 创建游标，用来执行SQL
cursor = conn.cursor()

# 示例：查询mysql库的user表
cursor.execute("SELECT user,host FROM mysql.user;")
result = cursor.fetchall()
print("查询结果：", result)

# 创建数据库 test_db
cursor.execute("CREATE DATABASE IF NOT EXISTS test_db;")
# 使用这个库
cursor.execute("USE test_db;")
# 创建学生表
cursor.execute("""
CREATE TABLE IF NOT EXISTS student(
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(50),
    age INT
);
""")
# 插入一条数据
cursor.execute("INSERT INTO student(name,age) VALUES ('张三',18);")
conn.commit() # 增删改必须commit提交
print("插入成功")

# 关闭游标、关闭连接
cursor.close()
conn.close()