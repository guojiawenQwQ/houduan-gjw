## part3 RabbitMQ
# 安装
![alt text](<../images/屏幕截图 2026-10-16 155303.png>)
![alt text](<../images/屏幕截图 2026-10-16 155400.png>)
![alt text](<../images/屏幕截图 2026-10-16 160714-1.png>)
![alt text](<../images/屏幕截图 2026-10-16 160632.png>)
# 01 把操作放到 MQ 里
1.  pymysql：Python ↔ MySQL 的桥梁
    redis：Python ↔ Redis 的桥梁
    pika：Python ↔ RabbitMQ 的桥梁
2. pika作用：
(1)建立连接，登录 RabbitMQ：pika.PlainCredentials、pika.ConnectionParameters
credentials = pika.PlainCredentials('账号', '密码')
connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', credentials=credentials))
#BlockingConnection：阻塞式连接，Blocking = 阻塞：同步连接方式。执行到这一行代码，程序会停在这里，一直等到连上 RabbitMQ 成功，或者抛出报错，才会继续往下跑代码。
#ConnectionParameters = Connection（连接）+ Parameters（参数），连接参数类，用来把连接需要的所有信息打包传给BlockingConnection。
(2)创建通道 channel：消息传输的管道
channel = connection.channel()
#connection：刚刚建立好的 RabbitMQ TCP 网络连接（一根物理电话线）
#.channel()：连接对象自带的方法，在这个 TCP 连接里面开辟一个虚拟通道
(3)声明队列：channel.queue_declare()
channel.queue_declare(queue='note_task_queue', durable=True)
#queue_declare()：声明队列，作用：检查这个队列存不存在；不存在就自动创建；已经存在，就什么也不做（不会报错）。
#durable=True：队列是持久化队列，RabbitMQ 服务重启之后，队列本身不会消失。
(4)发消息（生产者，你的 FastAPI 接口）:把笔记任务丢进队列
channel.basic_publish(...)
(5)收消息（consumer 消费者）：监听队列拿到任务，去操作 MySQL
channel.basic_consume()
3. 格式
(1)
try:

except Exception:
    raise HTTPException(status_code=500, detail="消息发送失败,请检查RabbitMQ服务")

(2)
try:
    if
    elif
    elif
    conn.commit()
except Exception as e:
    # 出错就进这里
    conn.rollback() # 回滚，撤销数据库改动
    print(f"任务失败: {e}")
finally:
    cursor.close()
    conn.close() 

4. 回调函数
def callback(ch, method, properties, body):  #参数顺序不能乱，名字可以自定义
必须写 basic_ack，不写的话 MQ 不会删除消息，消费者重启会重复消费！
# 02
1. 顺序性
问题：网络延迟会导致同一笔记的消息乱序，如删除消息先到达、新增消息后到达，引发异常。
解决：同一个笔记的消息使用相同路由键，发送至同一个队列，使用单个消费者消费，保证消息按发送顺序消费。
![alt text](<../images/屏幕截图 2026-10-17 133331.png>)
2. 幂等性
问题：网络异常会导致消息重复投递，多次新增笔记，产生重复数据。
解决：每条消息携带全局唯一 msg_id；消费者处理消息前，查询消息记录表判断该 msg_id 是否已处理。已处理则跳过；未处理执行业务，处理完成把 msg_id 存入记录表，保证重复消息不会重复执行业务逻辑。
![alt text](<../images/屏幕截图 2026-10-17 133415.png>)
3. 终端
![alt text](<../images/屏幕截图 2026-10-17 133625.png>)
![alt text](<../images/屏幕截图 2026-10-17 133718.png>)