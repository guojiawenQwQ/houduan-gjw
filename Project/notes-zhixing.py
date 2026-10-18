import pika
import json
import pymysql

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

# 收到消息后执行的回调函数
def callback(ch, method, properties, body): #ch（channel 的简写，通道对象），method 消息方法信息（元数据）
    #properties 消息属性，就是生产者发消息时 pika.BasicProperties(...) 设置的内容。#body 消息本体（最重要），task内容
    print("【收到任务】", body)
    task = json.loads(body)
    action = task["action"]
    msg_id = task["msg_id"]  # 获取消息唯一id
    # 真正在这里插入数据库
    conn = get_db_conn()
    cursor = conn.cursor()
    new_id = None
    try:
        # 幂等校验：查询这条msg_id是否已经处理完成
        cursor.execute("SELECT msg_id FROM msg_record WHERE msg_id=%s", (msg_id,))
        exist_row = cursor.fetchone()
        if exist_row:
            print(f"msg_id = {msg_id} 已经处理过，跳过本次业务！")
            ch.basic_ack(delivery_tag = method.delivery_tag) # 手动确认消息
            return
        # 消息没有处理过，执行笔记业务增删改
        if action == "add":
            sql = "INSERT INTO notes(title, content, user_id) VALUES(%s, %s, %s)"
            cursor.execute(sql, (task["title"], task["content"], task["user_id"]))
            new_id = cursor.lastrowid
            print(f"笔记保存成功,id={new_id}")
        elif action == "update":
            sql = "UPDATE notes SET title=%s, content=%s WHERE id=%s AND user_id=%s"
            cursor.execute(sql, (task["title"], task["content"], task["note_id"],task["user_id"]))
        elif action == "delete":
            sql = "DELETE FROM notes WHERE id=%s AND user_id=%s"
            cursor.execute(sql, (task["note_id"],task["user_id"]))
        conn.commit()
        # 业务执行成功！把msg_id存入msg_record，标记这条消息已经处理
        cursor.execute("INSERT INTO msg_record(msg_id) VALUES(%s)", (msg_id,))
        conn.commit()
        print(f"任务执行成功: {task}") #f 代表这是 f-string（格式化字符串），引号""里面，大括号 {} 可以写变量、表达式，Python 会自动把变量的值替换进去。
    # 告诉rabbitmq任务处理完成，消息可以删出了
        ch.basic_ack(delivery_tag = method.delivery_tag)
        #delivery_tag：消息编号，RabbitMQ 给每一条投递过来的消息分配的唯一标记号，用来区分不同消息。method.delivery_tag就是拿到当前这条消息的 tag
    except Exception as e: #as e：把捕获到的错误对象，起个名字叫e，后面可以拿到错误信息
        conn.rollback() #conn：MySQL 数据库连接对象，rollback() = 事务回滚，如果执行 SQL 中途出错，撤销这次数据库所有修改，恢复到执行之前的状态。
        print(f"任务失败，消息重回队列重试: {e}")
         # 失败，拒绝消息，重新放回队列
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    finally:
        cursor.close()
        conn.close()   
        
# 连接MQ，开始监听
def run_consumer():
    credentials = pika.PlainCredentials('admin', 'GJWgjw580098')
    connection = pika.BlockingConnection(
    pika.ConnectionParameters(host='localhost', credentials=credentials)
    )
    channel = connection.channel()
    channel.queue_declare(queue='note_task_queue', durable=True)
    channel.basic_qos(prefetch_count=1) #basic_qos：QOS = Quality of Service，服务质量控制，用来限制消费者一次最多拿多少条消息
    #prefetch_count=1：预取数量 = 1,MQ 先发第 1 条，等你 ack 确认完成，再发第 2 条，依次执行。
    channel.basic_consume(queue='note_task_queue', on_message_callback=callback)
    #channel：MQ 消息通道,basic_consume：开始消费消息，订阅队列.queue='note_task_queue'：要监听的队列名字,on_message_callback=callback：收到消息，自动执行 callback 函数
    print('消费者正在等待任务消息...')
    channel.start_consuming() #开启消息消费循环，程序阻塞等待 MQ 消息；有消息自动执行 callback，直到按下 Ctrl+C 关闭程序。
if __name__ == "__main__":
    run_consumer()