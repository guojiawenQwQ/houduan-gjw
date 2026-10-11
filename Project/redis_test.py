import redis

# 1.建立连接，默认本地localhost，端口6379
r = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True
)

# 测试连通性
print(r.ping()) # 返回True代表连接成功

# ========== String 字符串（最常用）==========
r.set("name", "张三")   # 存 key=name value=张三
print(r.get("name"))    # 读取：张三
r.setex("token", 10, "abc123") # 设置10秒过期

r.delete("name") # 删除key

# ========== Hash 哈希（存对象，类似字典，适合存用户信息）==========
r.hset("student:101", mapping={
    "name":"李四",
    "age":19
})
print(r.hgetall("student:101")) # 获取全部字段
print(r.hget("student:101","name")) # 获取单个字段

# ========== List 列表（队列）==========
r.lpush("mylist", "a", "b") # 左边插入
print(r.lrange("mylist",0,-1)) # 取出全部元素

# ========== 关闭连接（可选）==========
r.close()
