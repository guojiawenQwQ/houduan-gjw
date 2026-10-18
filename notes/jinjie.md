## Part1 接入 AI 的 API
1. 安装依赖
requests：用来在后端发送 HTTP 请求，去调用 AI 的 API
![alt text](<../images/屏幕截图 2026-10-17 202144.png>)
2. ![alt text](<../images/屏幕截图 2026-10-17 214007.png>)
3.  headers = {
        "api-key": MIMO_API_KEY, #鉴权
        "Content-Type": "application/json" # 告诉服务器：发送的数据是json格式
    }
4. #构造请求体,单轮对话，input直接填字符串
    question_text = {
        "input": question 
    }
5. requests.post 远程调用第三方 API
requests.post(
            url=AI_API_URL, # 请求目标地址，就是MiMo的API地址
            headers=headers, # 把上面写好的请求头传过去
            json=question_text, # 自动把req_body字典转为json字符串作为请求体
            timeout=120 # 超时时间：120秒，如果120秒没响应直接报错
        )
6. ai_text = result["output"][0]["content"] 
#从 MiMo 返回的数据里，找到 output 数组的第一条内容，取出 content 里面 AI 回答的文本，保存到 ai_text 变量。
result["output"] → [{"content": "你好！我是MiMo大模型，很高兴为你服务。"}]
result["output"][0] → {"content": "你好！我是MiMo大模型，很高兴为你服务。"}
result["output"][0]["content"] → "你好！我是MiMo大模型，很高兴为你服务。"

## Part2 会话记录
1. 执行流程
(1)前端传：session_id="chat01", question="解释FastAPI"
(2)代码检测 chat01 不存在，新建空列表
(3)追加用户消息进历史纪录：{"role":"user","content":"解释FastAPI"}
session_store[session_id].append({"role":"user", "content": question})
(4)把历史列表传给 MiMo，拿到 AI 回答
(5)把 AI 回答 {"role":"assistant", "content":"xxx"} 追加进历史
session_store[session_id].append({"role":"assistant", "content": ai_text})
(6)返回结果
(7)报错
 
## Part3 实现 Tool Use
1. 流程
(1)定义 Tool Schema（工具描述，发给大模型，告诉 AI 有什么工具可以调用）
告诉模型：有一个query_note_by_id函数，作用是根据笔记 id 查询笔记全文，需要参数note_id（整数）
(2)把 tools 数组放进请求体传给 MiMo 大模型
(3)拿到 AI 返回结果，判断有没有tool_calls
   如果有 tool_calls：AI 想要调用查询笔记工具
拿到工具名字、参数note_id
执行我们写好的 Python 函数，去 MySQL 查询这条笔记
把「AI 发起调用的记录」和「工具返回的笔记结果」追加进会话历史
再次发起请求，把更新后的完整会话丢给 AI，让 AI 基于笔记内容生成最终回答
   如果没有 tool_calls：直接返回 AI 普通对话回答给用户
最终只把 AI 整理好的自然语言返回给前端，中间工具调用细节对用户隐藏。
(4)两次requests.post
第一次：问 AI，你要不要调用工具？
第二次：工具执行完，把工具结果交给 AI，让 AI 总结回答用户。
2. 构建工具函数时几乎查询接口原代码不动，只改两处关键点：
把 raise HTTPException 全部删掉，改成返回文本字符串（HTTP 异常只能用于路由接口，内部函数不能抛）
原来的 return row / return json.loads(cache_data) 字典返回，改成包装成字符串返回，供给大模型读取
保留：Redis 缓存、分布式锁、缓存穿透（缓存空值）逻辑全部原样保留
3. 
(1)f "tool_calls" in model_msg and len(model_msg["tool_calls"]) > 0:
判断 AI 返回内容里面有没有工具调用请求。有 → 走工具调用分支；没有 → 普通聊天。
(2)func_args = json.loads(tool_call["function"]["arguments"])
AI 返回的参数是 JSON 字符串，用json.loads转为 Python 字典，取出note_id。
(3)session_store[session_id].append({"role": "tool", ...})
role="tool"，专门用来标记工具返回的结果，是 tool use 规定的消息角色。
4. tool_call内容
(1)id → tool_call_id
本次工具调用的编号。
后面我们返回工具结果的时候，"tool_call_id" 必须填这个 id，用来告诉大模型：这个结果，对应你刚才哪一次工具调用。
对应代码："tool_call_id": tool_call["id"]
(2)function.name
要调用的工具函数名称字符串。
必须和前面tools数组里定义的name一模一样（大小写也要一致）。
这里拿到query_note_by_id，后端判断名字，执行对应的 Python 函数。
(3)function.arguments
AI 生成的参数，是 JSON 字符串！
例子："{\"note_id\":2}"
❗重点：它不是 Python 字典，是字符串，所以必须用 json.loads() 转成字典，才能取note_id。
func_args = json.loads(tool_call["function"]["arguments"])
note_id = func_args["note_id"]
(4)type:"function" 固定标记，代表调用函数，作业里不用修改。
对应代码里
tool_call = model_msg["tool_calls"][0]

func_name = tool_call["function"]["name"]        # 拿函数名
func_args = json.loads(tool_call["function"]["arguments"]) # 解析参数字符串
note_id = func_args["note_id"]                   # 取出参数note_id
tool_call_id = tool_call["id"]                   # 获取调用编号，给role=tool消息使用
(5)完整的 tool_call 结构示例：
tool_call = {
    "id": "call_123456",          # 本次工具调用的唯一ID
    "type": "function",
    "function": {
        "name": "query_note_by_id",       # 要调用的函数名字（必须和我们tools定义一致）
        "arguments": "{\"note_id\":2}"    # 参数，**JSON字符串，不是字典！**
    }
}

## Part4
1. 做后端准备
#导入跨域中间件
from fastapi.middleware.cors import CORSMiddleware
#允许前端网页跨域访问后端接口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
2. 终端截图
![alt text](<../images/屏幕截图 2026-10-18 135541.png>)
![alt text](<../images/屏幕截图 2026-10-18 135552.png>)
![alt text](<../images/屏幕截图 2026-10-18 135513.png>)
![alt text](<../images/屏幕截图 2026-10-18 135528.png>)
3. 前端测试步骤：
在拓展商城中下载Live Server
右键index.html文件,open with Live Server
用浏览器打开文件
4. 测试前端截图
![alt text](<../images/屏幕截图 2026-10-18 151952.png>)
![alt text](<../images/屏幕截图 2026-10-18 140814.png>)
![alt text](<../images/屏幕截图 2026-10-18 161425.png>)
![alt text](<../images/屏幕截图 2026-10-18 161500.png>)
![alt text](<../images/屏幕截图 2026-10-18 162825.png>)
![alt text](<../images/屏幕截图 2026-10-18 182111.png>)
![alt text](<../images/屏幕截图 2026-10-18 182123.png>)
5. 测试后端截图
![alt text](<../images/屏幕截图 2026-10-18 185937.png>)
![alt text](<../images/屏幕截图 2026-10-18 190034.png>)
![alt text](<../images/屏幕截图 2026-10-18 190505.png>)
![alt text](<../images/屏幕截图 2026-10-18 205058.png>)
![alt text](<../images/屏幕截图 2026-10-18 205910.png>)
![alt text](<../images/屏幕截图 2026-10-18 205952.png>)
![alt text](<../images/屏幕截图 2026-10-18 210148.png>)
![alt text](<../images/屏幕截图 2026-10-18 210310.png>)
![alt text](<../images/屏幕截图 2026-10-18 210412.png>)
![alt text](<../images/屏幕截图 2026-10-18 210807.png>)
![alt text](<../images/屏幕截图 2026-10-18 210857.png>)

## 让AI agent修改的内容
![alt text](<../images/屏幕截图 2026-10-18 152334.png>)
![alt text](<../images/屏幕截图 2026-10-18 152353.png>)
![alt text](<../images/屏幕截图 2026-10-18 152413.png>)
![alt text](<../images/屏幕截图 2026-10-18 152429.png>)
