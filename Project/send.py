import pika

# 1.建立连接
connection = pika.BlockingConnection(
    pika.ConnectionParameters(host="localhost")
)
# 2.创建通道channel（几乎所有API都在channel上操作）
channel = connection.channel()

# 3.声明队列（不存在自动创建；多次声明不会重复创建，安全）
channel.queue_declare(queue="test_queue")

# 4.发布消息
# exchange='' 表示使用默认交换机；routing_key=队列名；body是消息内容
msg = "hello rabbitmq，这是一条消息"
channel.basic_publish(
    exchange="",
    routing_key="test_queue",
    body=msg
)
print(f"✅ 消息发送成功：{msg}")

# 关闭连接
connection.close()
