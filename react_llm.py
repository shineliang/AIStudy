import os
from openai import OpenAI# 也可以使用OpenAI或其他LLM提供商
from typing import Dict, Any

def react_with_llm(query: str, tools: Dict[str, Any] = None, max_iterations: int = 5):
    """
    使用ReAct模式调用LLM API
    
    Args:
        query: 用户查询
        tools: 可选的工具函数字典
        max_iterations: 最大迭代次数
        
    Returns:
        LLM的最终回答
    """
    # 初始化API客户端
    # client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    client = OpenAI(
    # api_key=os.getenv("deepseek_api_key"),  
    # base_url="https://api.deepseek.com/v1"
     api_key=os.getenv("AliDeep"),  
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
    
    # ReAct模式提示词
    react_prompt = """
你是一个解决问题的AI助手。请使用ReAct（思考和行动）方法解决问题，遵循以下格式：

思考：分析问题，考虑可能的方法和步骤。列出你的推理过程。
行动：基于你的思考，执行具体行动。可以是提供信息、计算结果或使用工具。
观察：记录行动的结果和新发现的信息。

重复以上步骤，直到你可以提供完整答案。
最终答案：提供问题的完整解决方案。

用户问题：{query}

开始你的解答：
"""
    
    # 如果有工具，添加工具说明
    if tools:
        tools_desc = "\n可用工具:\n"
        for tool_name, tool_info in tools.items():
            tools_desc += f"- {tool_name}: {tool_info['description']}\n  用法: {tool_info['usage']}\n"
        react_prompt = react_prompt.replace("用户问题", tools_desc + "\n用户问题")
    
    messages = [
        {"role": "user", "content": react_prompt.format(query=query)}
    ]
    
    # 调用API
    # response = client.chat.completions.create(
    #     model="claude-3-5-sonnet-20240620",  # 根据需要选择模型
    #     max_tokens=4000,
    #     messages=messages
    # )
    response = client.chat.completions.create(
        model="qwen-max",
        messages=messages,
    )
    # 如果需要实现多轮工具调用，这里可以添加解析响应并执行工具的逻辑
    
    return response.choices[0].message.content

# 使用示例
if __name__ == "__main__":
    # 定义可选工具
    available_tools = {
        "search": {
            "description": "在网络上搜索信息",
            "usage": "search(查询词)"
        },
        "calculate": {
            "description": "执行数学计算",
            "usage": "calculate(数学表达式)"
        }
    }
    
    user_question = "我需要设计一个电子商务网站的推荐系统，应该考虑哪些关键因素？"
    answer = react_with_llm(user_question, tools=available_tools)
    print(answer)
