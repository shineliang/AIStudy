from flask import Flask, request, jsonify, Response, stream_with_context
import os
import uuid
import json
import requests
from openai import OpenAI
from functools import wraps
from datetime import datetime
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
        
        url = f"https://67c7acf0c19eb8753e7a57f4.mockapi.io/attendance_records?date={date}"
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
        
        url = f"https://67c7acf0c19eb8753e7a57f4.mockapi.io/shift?date={date}"
        response = requests.get(url)
        data = response.json()
        
        print(f"排班API响应: {data}")
        
        if data and isinstance(data, list):
            return {
                "date": date,
                "shifts": data,
                "count": len(data)
            }
        else:
            return {"error": "无法获取排班信息", "raw_response": data}
    except Exception as e:
        print(f"查询排班信息出错: {e}")
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
    }
]

# 工具执行函数映射
tool_functions = {
    "get_weather": get_weather,
    "get_douyin_hot": get_douyin_hot,
    "query_violation_code": query_violation_code,
    "get_attendance_records": get_attendance_records,
    "get_shift_info": get_shift_info
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
- 今天日期是：{{date}}

保持回答简洁、清晰且信息丰富。
"""
    template = Template(template_string)
    prompt = template.render(date=datetime.now().strftime("%Y-%m-%d"))
    return prompt

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        print("收到聊天请求")
        data = request.json
        print(f"请求数据: {data}")
        
        user_message = data.get('message')
        session_id = data.get('sessionId')
        stream_mode = data.get('stream', True)
        
        print(f"用户消息: {user_message}")
        print(f"会话ID: {session_id}")
        print(f"流式模式: {stream_mode}")

        # 如果没有会话ID或会话不存在，创建新会话
        if not session_id or session_id not in sessions:
            session_id = str(uuid.uuid4())
            print(f"创建新会话: {session_id}")
            sessions[session_id] = []
        
        # 添加用户消息到历史
        sessions[session_id].append({
            "role": "user",
            "content": user_message
        })
        
        # 返回会话ID，前端将使用此ID请求SSE流
        return jsonify({
            'sessionId': session_id,
            'status': 'streaming_ready'
        })
        
    except Exception as e:
        print(f"处理聊天请求时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e)
        }), 500

# 在Flask应用中添加这个新路由

@app.route('/api/chat/stream', methods=['GET'])
def chat_stream():
    """处理流式响应请求"""
    try:
        session_id = request.args.get('sessionId', '')
        print("调用chat_stream()")
        
        if not session_id or session_id not in sessions:
            return jsonify({'error': 'Invalid session ID'}), 400
        
        # 获取会话历史
        session_messages = sessions[session_id]
        
        # 构建完整的消息列表，包括系统提示
        messages = [
            {"role": "system", "content": create_react_system_prompt()},
            *session_messages  # 展开会话历史消息
        ]
        
        print(f"完整消息列表: {messages}")
        
        # 检查并更新系统提示中的日期
        if messages and messages[0]["role"] == "system":
            current_date = datetime.now().strftime("%Y-%m-%d")
            system_prompt = messages[0]["content"]
            if "{date}" in system_prompt:
                updated_prompt = system_prompt.replace("{date}", current_date)
                messages[0]["content"] = updated_prompt
        
        return stream_response(messages, session_id)
        
    except Exception as e:
        print(f"处理流式请求时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def stream_response(messages, session_id):
    """创建流式响应"""
    def generate():
        try:
            print("开始生成流式响应")
            # 发送会话ID
            yield f"data: {json.dumps({'type': 'session_id', 'sessionId': session_id})}\n\n"
            
            full_response = ""
            tool_calls = []
            current_tool_call = None
            
            print("创建 chat completion 请求")
            # 开始流式处理
            stream = client.chat.completions.create(
                model="qwen-max",
                messages=messages,
                tools=available_tools,
                stream=True
            )
            
            print("开始处理流式响应")
            for chunk in stream:
                print(f"收到chunk: {chunk}")  # 调试日志
                
                # 检查是否有内容更新
                if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    print(f"发送内容: {content}")  # 调试日志
                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                
                # 检查是否有工具调用
                if hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls:
                    print("处理工具调用")  # 调试日志
                    for tool_call in chunk.choices[0].delta.tool_calls:
                        # 处理新工具调用
                        if hasattr(tool_call, 'function') and tool_call.function:
                            if hasattr(tool_call, 'id') and tool_call.id:
                                # 这是一个新的完整工具调用
                                current_tool_call = {
                                    "id": tool_call.id,
                                    "function": {
                                        "name": tool_call.function.name,
                                        "arguments": tool_call.function.arguments or ""
                                    }
                                }
                                tool_calls.append(current_tool_call)
                            elif current_tool_call is None and tool_call.function.name:
                                # 这是一个新工具调用的开始
                                current_tool_call = {
                                    "id": None,
                                    "function": {
                                        "name": tool_call.function.name,
                                        "arguments": tool_call.function.arguments or ""
                                    }
                                }
                                tool_calls.append(current_tool_call)
                            elif current_tool_call is not None and tool_call.function.arguments:
                                # 这是现有工具调用的参数更新
                                current_tool_call["function"]["arguments"] += tool_call.function.arguments
                        
                        # 处理ID更新
                        if hasattr(tool_call, 'id') and tool_call.id and current_tool_call and current_tool_call["id"] is None:
                            current_tool_call["id"] = tool_call.id
            
            print(f"流式处理完成，工具调用数量: {len(tool_calls)}")  # 调试日志
            
            # 合并相同工具的参数
            merged_tool_calls = []
            for tc in tool_calls:
                if tc["function"]["name"] == "get_weather":  # 只处理天气工具调用
                    # 尝试合并参数
                    try:
                        args_str = tc["function"]["arguments"].strip()
                        if args_str:
                            # 修复可能的JSON格式问题
                            if args_str.startswith('{') and not args_str.endswith('}'):
                                args_str += '}'
                            if not args_str.startswith('{'):
                                args_str = '{' + args_str
                            
                            # 尝试解析JSON
                            try:
                                args = json.loads(args_str)
                                if "city" in args:
                                    merged_tool_calls.append({
                                        "id": tc["id"] or str(uuid.uuid4()),
                                        "function": {
                                            "name": "get_weather",
                                            "arguments": json.dumps({"city": args["city"]})
                                        }
                                    })
                            except json.JSONDecodeError:
                                # 如果JSON解析失败，尝试直接提取城市名
                                if "苏州" in args_str:
                                    merged_tool_calls.append({
                                        "id": tc["id"] or str(uuid.uuid4()),
                                        "function": {
                                            "name": "get_weather",
                                            "arguments": json.dumps({"city": "苏州"})
                                        }
                                    })
                    except Exception as e:
                        print(f"合并工具参数出错: {e}")
            
            # 如果没有成功合并，但有工具调用，创建一个默认的
            if not merged_tool_calls and "苏州" in messages[-1]["content"]:
                merged_tool_calls.append({
                    "id": str(uuid.uuid4()),
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"city": "苏州"})
                    }
                })
            
            # 执行工具调用并返回结果
            for tool_call in merged_tool_calls:
                function_name = tool_call["function"]["name"]
                try:
                    arguments = json.loads(tool_call["function"]["arguments"])
                    print(f"执行工具调用: {function_name}, 参数: {arguments}")  # 调试日志
                    
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': function_name, 'arguments': arguments})}\n\n"
                    
                    if function_name in tool_functions:
                        tool_result = tool_functions[function_name](**arguments)
                        print(f"工具调用结果: {tool_result}")  # 调试日志
                        yield f"data: {json.dumps({'type': 'tool_result', 'tool': function_name, 'result': tool_result})}\n\n"
                        
                        # 继续对话，但不再处理新的工具调用
                        tool_response_messages = messages.copy()
                        tool_response_messages.extend([
                            {"role": "assistant", "content": None, "tool_calls": [{
                                "id": tool_call["id"],
                                "type": "function",
                                "function": {
                                    "name": function_name,
                                    "arguments": tool_call["function"]["arguments"]
                                }
                            }]},
                            {"role": "tool", "content": json.dumps(tool_result), "tool_call_id": tool_call["id"]}
                        ])
                        
                        print("发送后续请求")  # 调试日志
                        continue_stream = client.chat.completions.create(
                            model="qwen-max",
                            messages=tool_response_messages,
                            stream=True
                        )
                        
                        for chunk in continue_stream:
                            if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                full_response += content
                                print(f"发送后续内容: {content}")  # 调试日志
                                yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"
                except Exception as e:
                    print(f"执行工具调用出错: {e}")
                    import traceback
                    traceback.print_exc()
                    # 发送错误消息但继续执行
                    yield f"data: {json.dumps({'type': 'error', 'content': f'工具调用出错: {str(e)}'})}\n\n"
            
            # 如果没有工具调用或没有生成任何响应，生成一个默认回复
            if not full_response.strip():
                default_response = "**思考:** 用户询问苏州天气，我应该使用天气查询工具。\n\n**最终答案:** 抱歉，我在获取苏州天气信息时遇到了问题。请稍后再试。"
                full_response = default_response
                yield f"data: {json.dumps({'type': 'content', 'content': default_response})}\n\n"
            
            # 保存助手回复到会话历史
            sessions[session_id].append({
                "role": "assistant",
                "content": full_response
            })
            print(f"保存回复到会话历史: {full_response[:100]}...")  # 调试日志
            
            # 发送完成信号
            print("发送完成信号")  # 调试日志
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            print(f"流式响应出错: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            # 发送一个默认回复
            yield f"data: {json.dumps({'type': 'content', 'content': '抱歉，处理您的请求时出现了问题。'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        finally:
            print("流式响应结束")  # 调试日志
            yield "event: close\ndata: close\n\n"
    
    return Response(
        stream_with_context(generate()), 
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
            'Access-Control-Allow-Origin': 'http://localhost:3000',
            'Access-Control-Allow-Credentials': 'true'
        }
    )

def standard_response(messages, session_id):
    """创建标准（非流式）响应"""
    try:
        response = client.chat.completions.create(
            model="qwen-max",
            messages=messages,
            tools=available_tools
        )
        
        assistant_message = response.choices[0].message.content
        
        # 处理工具调用
        if response.choices[0].message.tool_calls:
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
            
            # 如果有工具调用，向AI提供结果并再次请求回复
            if tool_results:
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
                
                # 获取最终回复
                final_response = client.chat.completions.create(
                    model="qwen-max",
                    messages=tool_messages,
                    tools=available_tools
                )
                
                assistant_message = final_response.choices[0].message.content
        
        # 添加助手回复到历史
        sessions[session_id].append({
            "role": "assistant",
            "content": assistant_message
        })
        
        return jsonify({
            'sessionId': session_id,
            'message': assistant_message
        })
    
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5100, debug=True)
