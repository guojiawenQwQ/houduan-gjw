import pika

# 回调函数：收到消息自动执行这个函数
def callback(ch, method, properties, body):
    print(f"📩 收到消息：{body.decode('utf-8')}")

# 建立连接
connection = pika.BlockingConnection(
    pika.ConnectionParameters(host="localhost")
)
channel = connection.channel()

# 声明队列
channel.queue_declare(queue="test_queue")

# 订阅队列，设置回调函数
channel.basic_consume(
    queue="test_queue",
    on_message_callback=callback,
    auto_ack=True
)

print("🔍 等待接收消息，按 Ctrl+C 停止")
channel.start_consuming()
