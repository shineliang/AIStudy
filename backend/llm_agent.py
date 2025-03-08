from flask import Flask, request, jsonify, Response, stream_with_context
import os
import uuid
import json
import requests
from openai import OpenAI
from functools import wraps
from datetime import datetime, timedelta
from flask_cors import CORS
from jinja2 import Template

app = Flask(__name__)
# 配置 CORS，允许前端访问
CORS(app, supports_credentials=True, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000"],  # 明确指定前端域名
        "methods": ["GET", "POST", "OPTIONS"],  # 允许的方法
        "allow_headers": ["Content-Type", "Authorization"],  # 允许的请求头
        "expose_headers": ["Content-Type"],
        "max_age": 600,
        "supports_credentials": True
    }
})

# 模拟数据库，实际应用中应使用Redis或MongoDB
sessions = {}

# 初始化OpenAI客户端
client = OpenAI(
    api_key=os.environ.get("AliDeep"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )

# 工具定义
def get_weather(city):
    """调用高德地图API查询天气"""
    try:
        # 打印调试信息
        print(f"查询天气: {city}")
        apikey = os.environ.get("amapkey")
        # 高德地图天气API
        url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={city}&key={apikey}&extensions=all"
        response = requests.get(url)
        data = response.json()
        
        # 打印API响应
        print(f"天气API响应: {data}")
        
        if data.get("status") == "1":
            # 获取实时天气
            if data.get("lives"):
                live_weather = data["lives"][0]
                return {
                    "city": live_weather["city"],
                    "weather": live_weather["weather"],
                    "temperature": live_weather["temperature"],
                    "humidity": live_weather["humidity"],
                    "wind_direction": live_weather["winddirection"],
                    "wind_power": live_weather["windpower"],
                    "report_time": live_weather["reporttime"],
                    "type": "live"
                }
            # 获取天气预报
            elif data.get("forecasts"):
                forecast = data["forecasts"][0]
                casts = forecast["casts"]
                return {
                    "city": forecast["city"],
                    "adcode": forecast["adcode"],
                    "province": forecast["province"],
                    "report_time": forecast["reporttime"],
                    "forecasts": casts,
                    "type": "forecast"
                }
            else:
                return {"error": "无法获取天气信息", "raw_response": data}
        else:
            return {"error": f"天气API返回错误: {data.get('info', '未知错误')}", "raw_response": data}
    except Exception as e:
        print(f"查询天气出错: {e}")
        return {"error": str(e)}

def get_douyin_hot():
    """查询抖音热搜"""
    try:
        url = "https://apis.tianapi.com/douyinhot/index"
        data = {"key": os.environ.get("tianapikey")}
        response = requests.post(url, data=data)
        result = response.json()
        if result.get("code") == 200:
            return {
                "list": [item for item in result.get("result", {}).get("list", [])[:10]]
            }
        return {"error": "获取抖音热搜失败", "raw_response": result}
    except Exception as e:
        return {"error": str(e)}

def query_violation_code(code):
    """查询交通违章代码"""
    try:
        # 打印调试信息
        print(f"查询违章代码: {code}")
        
        url = "https://apis.tianapi.com/jtwfcode/index"
        data = {"key": os.environ.get("tianapikey"), "code": code}
        response = requests.post(url, data=data)
        result = response.json()
        
        # 打印API响应
        print(f"API响应: {result}")
        
        if result.get("code") == 200:
            return result.get("result", {})
        return {"error": "获取违章代码信息失败", "raw_response": result}
    except Exception as e:
        print(f"查询违章代码出错: {e}")
        return {"error": str(e)}

def get_attendance_records(date):
    """查询指定日期的考勤记录"""
    try:
        print(f"查询考勤记录: {date}")
        
        url = f"http://localhost:5200/attendace_records?date={date}"
        response = requests.get(url)
        data = response.json()
        
        print(f"考勤API响应: {data}")
        
        if data and isinstance(data, list):
            return {
                "date": date,
                "records": data,
                "count": len(data)
            }
        else:
            return {"error": "无法获取考勤记录", "raw_response": data}
    except Exception as e:
        print(f"查询考勤记录出错: {e}")
        return {"error": str(e)}

def get_shift_info(date):
    """查询指定日期的排班信息"""
    try:
        print(f"查询排班信息: {date}")
        
        # 模拟API调用，实际应用中应连接到真实数据源
        url = f"http://localhost:5200/shifts?date={date}"
        response = requests.get(url)
        data = response.json()
        
        print(f"排班API响应: {data}")
        
        if data and isinstance(data, list):
            return {
                "date": date,
                "records": data
            }
        else:
            return {"error": "未找到排班记录"}
    except Exception as e:
        print(f"查询排班信息出错: {e}")
        return {"error": str(e)}

def apply_leave(start_date=None, hours=None, reason=None):
    """创建请假申请链接"""
    try:
        # 检查必填参数
        if reason is None:
            return {
                "status": "error",
                "message": "缺少必填参数: 请假原因",
                "missing_param": "reason"
            }
            
        # 如果未指定日期，使用今天的日期
        if not start_date:
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        # 如果未指定小时数，使用默认值8小时
        if hours is None:
            hours = 8
            
        # 构建请假申请URL
        application_url = f"http://localhost:5200/leaves?date={start_date}&hours={hours}&reason={reason}"
        
        return {
            "status": "success",
            "message": "请假申请已创建",
            "start_date": start_date,
            "hours": hours,
            "reason": reason,
            "application_url": application_url
        }
    except Exception as e:
        return {"error": str(e)}

# 定义可用工具
available_tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，如北京、上海、广州等"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_douyin_hot",
            "description": "获取抖音热搜榜",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_violation_code",
            "description": "查询交通违章代码对应的违章内容、罚款金额和扣分",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "交通违章代码，如1301、1208等"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_attendance_records",
            "description": "查询指定日期的考勤记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "日期，格式为YYYY-MM-DD，如2025-03-07"
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_shift_info",
            "description": "查询指定日期的排班信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "日期，格式为YYYY-MM-DD，如2025-03-07"
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_leave",
            "description": "创建请假申请",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "请假开始日期，格式为YYYY-MM-DD，如2025-03-15"
                    },
                    "hours": {
                        "type": "number",
                        "description": "请假小时数，如4表示请假4小时"
                    },
                    "reason": {  # 新增必填参数示例
                        "type": "string", 
                        "description": "请假原因"
                    }
                },
                "required": ["reason"]  # 设置reason为必填参数
            }
        }
    }
]

# 工具执行函数映射
tool_functions = {
    "get_weather": get_weather,
    "get_douyin_hot": get_douyin_hot,
    "query_violation_code": query_violation_code,
    "get_attendance_records": get_attendance_records,
    "get_shift_info": get_shift_info,
    "apply_leave": apply_leave
}

def create_react_system_prompt():
    """创建ReAct模式的系统提示词"""
    template_string = """你是一个解决问题的AI助手。请使用ReAct（思考和行动）方法解决问题，并使用Markdown格式输出，遵循以下格式：

**思考:** 分析问题，考虑可能的方法和步骤。详细解释你的推理过程。

**行动:** 明确指出你要采取的行动，例如调用特定工具。

**观察:** 记录工具返回的结果或你的观察。

**最终答案:** 提供最终的、全面的回答。

你的回答应该使用Markdown格式，包括：
- 使用**粗体**强调重要内容
- 使用*斜体*表示次要信息
- 使用`代码块`展示代码或特殊格式内容
- 使用列表和表格组织信息
- 使用标题层级结构化内容
- 工具的返回内容中的关键信息，应当保持原样呈现，不要擅自修改
- 特别注意：工具返回的 name、人名、日期、时间、地点 等关键信息必须完全准确地保留，不得更改或替换

当你需要调用工具但缺少必要参数时：
1. 不要用默认值或猜测值调用工具
2. 在**思考**环节识别缺失的必填参数
3. 明确告诉用户需要提供哪些具体信息
4. 等待用户提供完整参数后再调用工具

今天日期是：{{date}}

保持回答简洁、清晰且信息丰富。
"""
    template = Template(template_string)
    return template.render(date=datetime.now().strftime("%Y-%m-%d"))

def create_or_get_session(session_id):
    """创建新会话或获取现有会话"""
    if not session_id or session_id not in sessions:
        session_id = str(uuid.uuid4())
        sessions[session_id] = []
    return session_id

def add_message_to_session(session_id, role, content):
    """添加消息到会话历史"""
    sessions[session_id].append({"role": role, "content": content})

def get_session_messages(session_id):
    """获取会话历史消息"""
    return sessions[session_id]

def build_complete_messages(session_id):
    """构建完整的消息列表，包括系统提示"""
    return [
        {"role": "system", "content": create_react_system_prompt()},
        *get_session_messages(session_id)
    ]

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        print("收到聊天请求")
        data = request.json
        user_message = data.get('message')
        session_id = data.get('sessionId')
        
        session_id = create_or_get_session(session_id)
        add_message_to_session(session_id, "user", user_message)
        
        return jsonify({
            'sessionId': session_id,
            'status': 'streaming_ready'
        })
        
    except Exception as e:
        print(f"处理聊天请求时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/stream', methods=['GET'])
def chat_stream():
    """处理流式响应请求"""
    try:
        session_id = request.args.get('sessionId', '')
        
        if not session_id or session_id not in sessions:
            return jsonify({'error': 'Invalid session ID'}), 400
        
        messages = build_complete_messages(session_id)
        return stream_response(messages, session_id)
        
    except Exception as e:
        print(f"处理流式请求时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def stream_response(messages, session_id):
    """创建流式响应"""
    return Response(
        stream_with_context(generate_stream(messages, session_id)), 
        mimetype='text/event-stream',
        headers=get_sse_headers()
    )

def get_sse_headers():
    """获取SSE响应头"""
    return {
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
        'Access-Control-Allow-Origin': 'http://localhost:3000',
        'Access-Control-Allow-Credentials': 'true'
    }

def generate_stream(messages, session_id):
    """生成流式响应内容"""
    try:
        yield send_session_id(session_id)
        
        full_response, tool_calls = process_initial_response(messages)
        
        for tool_call in merge_tool_calls(tool_calls):
            yield from process_tool_call(tool_call, messages, full_response, session_id)
        
        full_response = ensure_complete_response(messages, full_response, send_content)
        
        add_message_to_session(session_id, "assistant", full_response)
        yield send_done_signal()
        
    except Exception as e:
        yield from handle_stream_error(e, send_content)
    finally:
        yield "event: close\ndata: close\n\n"

def send_session_id(session_id):
    """发送会话ID"""
    return f"data: {json.dumps({'type': 'session_id', 'sessionId': session_id})}\n\n"

def send_content(content):
    """发送内容块"""
    return f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

def send_tool_call(tool_name, arguments):
    """发送工具调用信息"""
    return f"data: {json.dumps({'type': 'tool_call', 'tool': tool_name, 'arguments': arguments})}\n\n"

def send_tool_result(tool_name, result):
    """发送工具调用结果"""
    return f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'result': result})}\n\n"

def send_error(error_message):
    """发送错误信息"""
    return f"data: {json.dumps({'type': 'error', 'content': error_message})}\n\n"

def send_done_signal():
    """发送完成信号"""
    return f"data: {json.dumps({'type': 'done'})}\n\n"

def process_initial_response(messages):
    """处理初始响应并收集工具调用"""
    full_response = ""
    tool_calls = []
    current_tool_call = None
    
    stream = client.chat.completions.create(
        model="qwen-max",
        messages=messages,
        tools=available_tools,
        stream=True
    )
    
    for chunk in stream:
        result = process_chunk(chunk, full_response, tool_calls, current_tool_call)
        if isinstance(result, tuple) and len(result) == 3:
            full_response, tool_calls, current_tool_call = result
    
    return full_response, tool_calls

def process_chunk(chunk, full_response, tool_calls, current_tool_call):
    """处理响应块，更新内容和工具调用"""
    if has_content(chunk):
        content = chunk.choices[0].delta.content
        full_response += content
    
    if has_tool_calls(chunk):
        tool_calls, current_tool_call = update_tool_calls(
            chunk.choices[0].delta.tool_calls, 
            tool_calls, 
            current_tool_call
        )
    
    return full_response, tool_calls, current_tool_call

def has_content(chunk):
    """检查响应块是否包含内容"""
    return hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content

def has_tool_calls(chunk):
    """检查响应块是否包含工具调用"""
    return hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls

def update_tool_calls(new_tool_calls, tool_calls, current_tool_call):
    """更新工具调用列表"""
    for tool_call in new_tool_calls:
        if is_new_complete_tool_call(tool_call):
            current_tool_call = create_complete_tool_call(tool_call)
            tool_calls.append(current_tool_call)
        elif is_new_tool_call_start(tool_call, current_tool_call):
            current_tool_call = create_new_tool_call(tool_call)
            tool_calls.append(current_tool_call)
        elif is_tool_call_argument_update(tool_call, current_tool_call):
            current_tool_call["function"]["arguments"] += tool_call.function.arguments
        
        if is_tool_call_id_update(tool_call, current_tool_call):
            current_tool_call["id"] = tool_call.id
    
    return tool_calls, current_tool_call

def is_new_complete_tool_call(tool_call):
    """检查是否是新的完整工具调用"""
    return (hasattr(tool_call, 'function') and tool_call.function and
            hasattr(tool_call, 'id') and tool_call.id)

def create_complete_tool_call(tool_call):
    """创建完整的工具调用对象"""
    return {
        "id": tool_call.id,
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments or ""
        }
    }

def is_new_tool_call_start(tool_call, current_tool_call):
    """检查是否是新工具调用的开始"""
    return (current_tool_call is None and 
            hasattr(tool_call, 'function') and 
            tool_call.function and 
            tool_call.function.name)

def create_new_tool_call(tool_call):
    """创建新的工具调用对象"""
    return {
        "id": None,
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments or ""
        }
    }

def is_tool_call_argument_update(tool_call, current_tool_call):
    """检查是否是工具调用参数更新"""
    return (current_tool_call is not None and 
            hasattr(tool_call, 'function') and 
            tool_call.function and 
            tool_call.function.arguments)

def is_tool_call_id_update(tool_call, current_tool_call):
    """检查是否是工具调用ID更新"""
    return (hasattr(tool_call, 'id') and 
            tool_call.id and 
            current_tool_call and 
            current_tool_call["id"] is None)

def merge_tool_calls(tool_calls):
    """合并工具调用参数"""
    merged_calls = []
    for tc in tool_calls:
        try:
            args_str = tc["function"]["arguments"].strip()
            if not args_str:
                continue
                
            args_str = fix_json_format(args_str)
            args = json.loads(args_str)
            
            merged_calls.append({
                "id": tc["id"] or str(uuid.uuid4()),
                "function": {
                    "name": tc["function"]["name"],
                    "arguments": json.dumps(args)
                }
            })
        except Exception as e:
            print(f"合并工具参数出错: {e}")
    
    # 如果没有成功合并但有工具调用，使用第一个工具调用
    if not merged_calls and tool_calls:
        add_first_tool_call(merged_calls, tool_calls)
    
    return merged_calls

def fix_json_format(args_str):
    """修复可能的JSON格式问题"""
    if args_str.startswith('{') and not args_str.endswith('}'):
        args_str += '}'
    if not args_str.startswith('{'):
        args_str = '{' + args_str
    return args_str

def add_first_tool_call(merged_calls, tool_calls):
    """添加第一个工具调用到合并列表"""
    first_tool = tool_calls[0]
    merged_calls.append({
        "id": first_tool["id"] or str(uuid.uuid4()),
        "function": {
            "name": first_tool["function"]["name"],
            "arguments": first_tool["function"]["arguments"] or "{}"
        }
    })

def process_tool_call(tool_call, messages, full_response, session_id):
    """处理单个工具调用"""
    function_name = tool_call["function"]["name"]
    try:
        arguments = json.loads(tool_call["function"]["arguments"])
        yield send_tool_call(function_name, arguments)
        
        if function_name in tool_functions:
            tool_result = execute_tool(function_name, arguments)
            yield send_tool_result(function_name, tool_result)
            
            tool_response_messages = build_tool_response_messages(
                messages, tool_call, function_name, tool_result
            )
            
            yield from continue_conversation(
                tool_response_messages, full_response
            )
    except Exception as e:
        yield send_error(f"工具调用出错: {str(e)}")

def execute_tool(function_name, arguments):
    """执行工具函数"""
    return tool_functions[function_name](**arguments)

def build_tool_response_messages(messages, tool_call, function_name, tool_result):
    """构建包含工具响应的消息列表"""
    tool_response_messages = messages.copy()
    tool_response_messages.extend([
        {
            "role": "assistant", 
            "content": None, 
            "tool_calls": [{
                "id": tool_call["id"],
                "type": "function",
                "function": {
                    "name": function_name,
                    "arguments": tool_call["function"]["arguments"]
                }
            }]
        },
        {
            "role": "tool", 
            "content": json.dumps(tool_result, ensure_ascii=False), 
            "tool_call_id": tool_call["id"]
        }
    ])
    return tool_response_messages

def continue_conversation(tool_response_messages, full_response):
    """继续对话，处理工具调用后的响应"""
    continue_stream = client.chat.completions.create(
        model="qwen-max",
        messages=tool_response_messages,
        stream=True
    )
    
    received_content = False
    for chunk in continue_stream:
        if has_content(chunk):
            content = chunk.choices[0].delta.content
            full_response += content
            yield send_content(content)
            received_content = True
    
    if not received_content:
        yield from handle_missing_content(tool_response_messages)

def handle_missing_content(tool_response_messages):
    """处理未收到内容的情况"""
    try:
        complete_response = client.chat.completions.create(
            model="qwen-max",
            messages=tool_response_messages
        )
        
        if complete_response.choices[0].message.content:
            content = complete_response.choices[0].message.content
            yield send_content(content)
    except Exception as e:
        print(f"获取完整响应失败: {e}")

def ensure_complete_response(messages, full_response, send_func):
    """确保响应完整，包含最终答案"""
    if needs_completion(full_response):
        full_response = complete_response(messages, full_response, send_func)
    
    if not full_response.strip():
        full_response = provide_default_response(send_func)
    
    return full_response

def needs_completion(full_response):
    """检查响应是否需要补充完整"""
    return (full_response.strip() and 
            "**思考:**" in full_response and 
            "**最终答案:**" not in full_response)

def complete_response(messages, full_response, send_func):
    """补充完整响应"""
    try:
        completion_messages = build_completion_messages(messages, full_response)
        completion_response = get_completion_response(completion_messages)
        
        if completion_response.choices[0].message.content:
            additional_content = format_additional_content(
                completion_response.choices[0].message.content
            )
            
            full_response += additional_content
            send_func(send_content(additional_content))
    except Exception as e:
        print(f"补充最终答案失败: {e}")
        default_answer = "\n\n**最终答案:** 根据查询结果，这是相关信息的总结。"
        full_response += default_answer
        send_func(send_content(default_answer))
    
    return full_response

def build_completion_messages(messages, full_response):
    """构建补充完整响应的消息列表"""
    completion_messages = messages.copy()
    completion_messages.append({
        "role": "assistant",
        "content": full_response
    })
    completion_messages.append({
        "role": "user",
        "content": "请继续你的回答，提供最终答案。"
    })
    return completion_messages

def get_completion_response(completion_messages):
    """获取补充响应"""
    return client.chat.completions.create(
        model="qwen-max",
        messages=completion_messages
    )

def format_additional_content(content):
    """格式化补充内容"""
    if "**最终答案:**" not in content:
        content = "\n\n**最终答案:** " + content
    return content

def provide_default_response(send_func):
    """提供默认响应"""
    default_response = "**思考:** 我需要分析用户的问题并提供适当的回答。\n\n**最终答案:** 抱歉，我在处理您的请求时遇到了问题。请稍后再试。"
    send_func(send_content(default_response))
    return default_response

def handle_stream_error(error, send_func):
    """处理流式响应错误"""
    print(f"流式响应出错: {error}")
    import traceback
    traceback.print_exc()
    yield send_error(str(error))
    yield send_func('抱歉，处理您的请求时出现了问题。')
    yield send_done_signal()

def standard_response(messages, session_id):
    """创建标准（非流式）响应"""
    try:
        response = get_initial_response(messages)
        assistant_message = response.choices[0].message.content
        
        if response.choices[0].message.tool_calls:
            tool_results = process_standard_tool_calls(response, messages)
            if tool_results:
                assistant_message = get_final_response(messages, response, tool_results)
        
        add_message_to_session(session_id, "assistant", assistant_message)
        
        return jsonify({
            'sessionId': session_id,
            'message': assistant_message
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_initial_response(messages):
    """获取初始响应"""
    return client.chat.completions.create(
        model="qwen-max",
        messages=messages,
        tools=available_tools
    )

def process_standard_tool_calls(response, messages):
    """处理标准模式下的工具调用"""
    tool_results = []
    for tool_call in response.choices[0].message.tool_calls:
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        
        if function_name in tool_functions:
            result = tool_functions[function_name](**arguments)
            tool_results.append({
                "tool": function_name,
                "arguments": arguments,
                "result": result
            })
    return tool_results

def get_final_response(messages, response, tool_results):
    """获取包含工具调用结果的最终响应"""
    tool_messages = build_standard_tool_messages(messages, response, tool_results)
    
    final_response = client.chat.completions.create(
        model="qwen-max",
        messages=tool_messages,
        tools=available_tools
    )
    
    return final_response.choices[0].message.content

def build_standard_tool_messages(messages, response, tool_results):
    """构建包含工具调用结果的消息列表"""
    tool_messages = messages.copy()
    for i, tool_call in enumerate(response.choices[0].message.tool_calls):
        tool_messages.append({
            "role": "assistant", 
            "content": None,
            "tool_calls": [{
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                }
            }]
        })
        tool_messages.append({
            "role": "tool",
            "content": json.dumps(tool_results[i]["result"]),
            "tool_call_id": tool_call.id
        })
    return tool_messages

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5100, debug=True)
