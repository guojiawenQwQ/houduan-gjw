from fastapi import FastAPI
app = FastAPI()
@app.get("/")
def read_root():
  return {"msg":"Hello World From FastAPI:"}
#新增hello接口
@app.get("/hello")
def hello():
  return {"msg":"Hello from Web Application!"}