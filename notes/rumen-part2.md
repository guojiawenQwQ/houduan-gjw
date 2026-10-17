## Part 2 缓存- Redis 

# 01 引入查询缓存
1. 连接Redis
redis_client = redis.Redis(
    host="localhost",
    port=6379,
    db=0,
    decode_responses=True
)
2. 常用 Redis 指令（Python 代码）
前提：WSL 执行 sudo service redis-server start 启动 redis 服务
(1)set：写入键值对（永久保存，不自动过期）
redis_client.set("note:1", "hello")-->(key,value)
(2)setex：写入 + 设置过期时间(秒)
redis_client.setex("note:1", 300, json.dumps(row))
(3)get：根据 key 读取数据
data = redis_client.get("note:1")# 有数据返回字符串；找不到返回 None
(4)delete：删除缓存（很重要！更新 / 删除笔记的时候要清缓存）
redis_client.delete("note:1")
(5)exists 判断 key 是否存在
if redis_client.exists("note:1"):
    print("缓存存在")
(6)expire：给已存在的 key 设置过期时间(秒)
redis_client.expire("note:1", 300)
(7)把变量的值塞到字符串里,f""：f-string，python 的字符串拼接语法，大括号{}里面放变量，
cache_key = f"note:{note_id}"
3. json
json.dumps() → 序列化：Python 对象 → JSON 字符串（存入 Redis）
json.loads() → 反序列化：JSON 字符串 → Python 对象（读出来用）
# 02
1. 缓存一致性：数据库更新后，清理旧缓存，保证缓存和数据库数据一致。
cache_key = f"note:{note_id}"
redis_client.delete(cache_key)
2. 缓存穿透：查询不存在的数据，直接打到 MySQL；解决：缓存空结果。
if not row:
        cache_key = f"note:{note_id}"
        redis_client.setex(cache_key,3600, json.dumps({"msg":"笔记不存在"}))
        raise HTTPException(status_code=404, detail="笔记不存在或者不是你的笔记")
3. 缓存击穿：热点 key 缓存过期，大量请求同时访问数据库；解决：Redis 互斥锁，即缓存过期的时候，只放一个请求去查询 MySQL 并且更新缓存；其余请求等待，不要同时查数据库。
lock_key = f"lock:note:{note_id}"  # 锁的key
#尝试获取锁，nx:不存在才设置，ex:锁超时时间，防止死锁
    lock_ok = redis_client.set(lock_key, "1", nx=True, ex=10)
    if not lock_ok:
        # 获取锁失败 → 直接返回，或者短暂重试
        raise HTTPException(status_code=429, detail="请求繁忙，请重试")
    try:
        # 获取锁成功，查询MySQL
        return row
    finally:
        # 无论成功失败，最后一定要释放锁！
        redis_client.delete(lock_key)

