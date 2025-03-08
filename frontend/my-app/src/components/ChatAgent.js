// src/components/ChatAgent.js
import React, { useState, useEffect, useRef } from 'react';
import './ChatAgent.css';
import ReactMarkdown from 'react-markdown';

const ChatAgent = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [streamingMessage, setStreamingMessage] = useState('');
  const [currentToolCall, setCurrentToolCall] = useState(null);
  const [currentToolResult, setCurrentToolResult] = useState(null);
  const messageEndRef = useRef(null);
  const eventSourceRef = useRef(null);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const streamingMessageRef = useRef('');
  const [showDebug, setShowDebug] = useState(false);
  const [debugLogs, setDebugLogs] = useState([]);

  // 自动滚动到最新消息
  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingMessage]);

  // 组件卸载时清理 SSE 连接
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // 检查是否需要显示滚动按钮
  const checkScrollPosition = () => {
    if (!messagesContainerRef.current) return;
    
    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
    // 如果滚动位置距离底部超过200px，显示滚动按钮
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 200;
    setShowScrollButton(!isNearBottom);
  };
  
  // 滚动到底部的函数
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };
  
  // 监听消息容器的滚动事件
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (container) {
      container.addEventListener('scroll', checkScrollPosition);
      return () => container.removeEventListener('scroll', checkScrollPosition);
    }
  }, []);
  
  // 当消息更新时检查滚动位置
  useEffect(() => {
    checkScrollPosition();
  }, [messages, streamingMessage, currentToolCall, currentToolResult]);

  // 在 useEffect 中同步 streamingMessage 到 ref
  useEffect(() => {
    streamingMessageRef.current = streamingMessage;
  }, [streamingMessage]);

  // 添加调试日志 - 修改为只保留工具调用相关记录
  const addDebugLog = (type, data) => {
    // 只有工具调用和结果才添加到日志
    if (type === 'tool-call' || type === 'tool-result') {
      setDebugLogs(prev => [...prev, {
        id: Date.now(),
        timestamp: new Date().toLocaleTimeString(),
        type,
        data
      }]);
    }
  };
  
  // 清除调试日志
  const clearDebugLogs = () => {
    setDebugLogs([]);
  };

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const userMessage = { type: 'user', content: input };
    const currentInput = input;
    
    setMessages(prev => [...prev, userMessage]);
    setLoading(true);
    setStreamingMessage('');
    setInput('');
    
    // 在新对话开始时重置工具调用和结果
    setCurrentToolCall(null);
    setCurrentToolResult(null);
    
    // 关闭之前的连接
    if (eventSourceRef.current) {
        console.log("关闭现有SSE连接");
        eventSourceRef.current.close();
        eventSourceRef.current = null;
    }

    try {
        console.log("发送聊天请求");
        const response = await fetch('http://localhost:5100/api/chat', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                message: currentInput,
                sessionId: sessionId || '',
                stream: true
            })
        });
        
        console.log("收到初始响应:", response);
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`服务器响应错误 ${response.status}: ${errorText}`);
        }
        
        const data = await response.json();
        console.log("解析响应数据:", data);
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        if (!data.sessionId) {
            throw new Error("服务器未返回会话ID");
        }
        
        // 设置会话ID
        setSessionId(data.sessionId);
        
        // 构建SSE URL
        const streamUrl = `http://localhost:5100/api/chat/stream?sessionId=${data.sessionId}`;
        console.log("准备连接SSE:", streamUrl);
        
        // 创建新的EventSource
        const eventSource = new EventSource(streamUrl);
        eventSourceRef.current = eventSource;
        
        // 设置事件处理器
        eventSource.onopen = () => {
            console.log("SSE连接已打开");
        };
        
        eventSource.onerror = (error) => {
            console.error("SSE错误:", error);
            if (eventSource.readyState === EventSource.CLOSED) {
                console.log("SSE连接已关闭");
                setLoading(false);
                eventSource.close();
                eventSourceRef.current = null;
                
                // 只在没有收到任何消息时显示错误
                if (!streamingMessageRef.current) {
                    setMessages(prev => [...prev, {
                        type: 'error',
                        content: "连接已断开，请重试"
                    }]);
                }
            }
        };
        
        eventSource.onmessage = (event) => {
            console.log("收到SSE消息:", event.data);
            try {
                const data = JSON.parse(event.data);
                handleStreamMessage(data);
            } catch (error) {
                console.error("处理SSE消息出错:", error);
            }
        };
        
    } catch (error) {
        console.error("请求失败:", error);
        setMessages(prev => [...prev, {
            type: 'error',
            content: `错误: ${error.message}`
        }]);
        setLoading(false);
    }
};

// 修改消息处理函数
const handleStreamMessage = React.useCallback((data) => {
    console.log("处理流消息:", data);
    switch (data.type) {
        case 'session_id':
            console.log("收到会话ID:", data.sessionId);
            break;
            
        case 'content':
            setStreamingMessage(prev => {
                const newMessage = prev + data.content;
                streamingMessageRef.current = newMessage;
                return newMessage;
            });
            break;
            
        case 'tool_call':
            console.log("工具调用:", data);
            setCurrentToolCall(prev => {
                addDebugLog('tool-call', data);
                return data;
            });
            break;
            
        case 'tool_result':
            console.log("工具结果:", data);
            setCurrentToolResult(prev => {
                addDebugLog('tool-result', data);
                return data;
            });
            break;
            
        case 'error':
            console.error("流错误:", data.content);
            setMessages(prev => [...prev, {
                type: 'error',
                content: data.content
            }]);
            break;
            
        case 'done':
            console.log("对话完成");
            setLoading(false);
            
            // 使用函数式更新确保状态更新的顺序性
            setMessages(prev => {
                const newMessages = [...prev];
                if (streamingMessageRef.current) {
                    newMessages.push({ 
                        type: 'ai', 
                        content: streamingMessageRef.current 
                    });
                } else {
                    newMessages.push({ 
                        type: 'ai', 
                        content: "抱歉，我无法处理您的请求。请稍后再试。" 
                    });
                }
                return newMessages;
            });
            
            // 关闭连接
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
                eventSourceRef.current = null;
            }
            
            // 重置状态 - 只重置流式消息，保留工具调用和结果
            setTimeout(() => {
                setStreamingMessage('');
                streamingMessageRef.current = '';
                // 不再重置工具调用和结果
                // setCurrentToolCall(null);
                // setCurrentToolResult(null);
            }, 100);
            break;
            
        default:
            console.log("未知消息类型:", data);
    }
}, [addDebugLog]);

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 修改 renderReactContent 函数，增强表格处理能力
  const renderReactContent = (content) => {
    if (!content) return null;
    
    // 尝试修复表格格式问题
    let fixedContent = content;
    
    // 检测表格行并确保它们有正确的格式
    const tableRowRegex = /\|(.+)\|/g;
    const tableLines = content.split('\n');
    let hasTable = false;
    let tableStartIndex = -1;
    
    // 检测表格并添加分隔行
    for (let i = 0; i < tableLines.length; i++) {
      if (tableLines[i].trim().match(/\|(.+)\|/) && !hasTable) {
        hasTable = true;
        tableStartIndex = i;
        
        // 检查下一行是否为分隔行
        const nextLine = i + 1 < tableLines.length ? tableLines[i + 1] : '';
        if (!nextLine.includes('---') && !nextLine.includes('===')) {
          // 计算列数
          const columns = tableLines[i].split('|').filter(cell => cell.trim()).length;
          let separatorLine = '|';
          for (let j = 0; j < columns; j++) {
            separatorLine += ' --- |';
          }
          // 插入分隔行
          tableLines.splice(i + 1, 0, separatorLine);
          i++; // 跳过新插入的行
        }
      }
    }
    
    if (hasTable) {
      fixedContent = tableLines.join('\n');
    }
    
    return (
      <ReactMarkdown
        components={{
          // 自定义表格组件渲染
          table: ({node, ...props}) => (
            <div className="table-container">
              <table className="markdown-table" {...props} />
            </div>
          ),
          thead: ({node, ...props}) => <thead {...props} />,
          tbody: ({node, ...props}) => <tbody {...props} />,
          tr: ({node, ...props}) => <tr {...props} />,
          th: ({node, ...props}) => <th className="markdown-th" {...props} />,
          td: ({node, ...props}) => <td className="markdown-td" {...props} />
        }}
      >
        {fixedContent}
      </ReactMarkdown>
    );
  };

  // 修改工具结果格式化函数，确保数据更清晰
  const formatToolResult = (result) => {
    if (!result) return null;
    
    try {
      if (result.error) {
        return (
          <div className="tool-error">
            <div className="error-message">{result.error}</div>
          </div>
        );
      }
      
      // 根据工具类型格式化结果
      switch (result.tool) {
        case 'get_shift_info':
          // 排班信息格式化 - 保留原始内容
          if (result.result.shifts && Array.isArray(result.result.shifts)) {
            return (
              <div className="shift-result tool-result">
                <h3>{result.result.date} 排班信息</h3>
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>姓名</th>
                      <th>日期</th>
                      <th>详情</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.result.shifts.map((shift, index) => (
                      <tr key={index}>
                        <td>{shift.id}</td>
                        <td style={{color: 'red', fontWeight: 'bold'}}>{shift.name}</td>
                        <td>{shift.date}</td>
                        <td>{shift.details}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="raw-data">
                  <details>
                    <summary>原始数据</summary>
                    <pre>{JSON.stringify(result.result, null, 2)}</pre>
                  </details>
                </div>
              </div>
            );
          }
          return <pre>{JSON.stringify(result.result, null, 2)}</pre>;
          
        case 'apply_leave':
          // 请假申请结果格式化
          if (result.result.status === "success") {
            return (
              <div className="leave-application-result tool-result">
                <h3>请假申请</h3>
                <div className="leave-details">
                  <p><strong>开始日期:</strong> {result.result.start_date}</p>
                  <p><strong>请假时长:</strong> {result.result.hours} 小时</p>
                  <p><strong>状态:</strong> <span className="success-status">已创建</span></p>
                  <div className="application-link">
                    <p>你可以点击以下链接进行请假申请:</p>
                    <a 
                      href={result.result.application_url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="leave-link"
                    >
                      前往请假系统
                    </a>
                  </div>
                </div>
                <div className="raw-data">
                  <details>
                    <summary>原始数据</summary>
                    <pre>{JSON.stringify(result.result, null, 2)}</pre>
                  </details>
                </div>
              </div>
            );
          }
          return <pre>{JSON.stringify(result.result, null, 2)}</pre>;
          
        // 其他工具类型的处理...
        
        default:
          return <pre>{JSON.stringify(result.result, null, 2)}</pre>;
      }
    } catch (error) {
      console.error('Error formatting tool result:', error);
      return <pre>{JSON.stringify(result, null, 2)}</pre>;
    }
  };

  // 辅助函数：格式化日期
  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    const weekday = weekdays[date.getDay()];
    return `${date.getMonth() + 1}月${date.getDate()}日 ${weekday}`;
  };

  // 辅助函数：根据天气状况返回对应图标
  const getWeatherIcon = (weather) => {
    const weatherIcons = {
      '晴': '☀️',
      '多云': '⛅',
      '阴': '☁️',
      '小雨': '🌦️',
      '中雨': '🌧️',
      '大雨': '🌧️',
      '暴雨': '⛈️',
      '雷阵雨': '⛈️',
      '小雪': '🌨️',
      '中雪': '🌨️',
      '大雪': '❄️',
      '雾': '🌫️',
      '霾': '😷',
    };
    
    // 尝试精确匹配
    if (weatherIcons[weather]) {
      return weatherIcons[weather];
    }
    
    // 尝试模糊匹配
    for (const key in weatherIcons) {
      if (weather.includes(key)) {
        return weatherIcons[key];
      }
    }
    
    // 默认图标
    return '🌈';
  };

  // 渲染调试日志项
  const renderDebugLogItem = (log) => {
    switch (log.type) {
      case 'user-message':
        return (
          <div className="debug-user-message">
            <div className="debug-header">用户消息</div>
            <div className="debug-content">{log.data}</div>
          </div>
        );
        
      case 'content':
        return (
          <div className="debug-content-chunk">
            <div className="debug-header">内容片段</div>
            <div className="debug-content">{log.data}</div>
          </div>
        );
        
      case 'tool-call':
        return (
          <div className="debug-tool-call">
            <div className="debug-header">工具调用: {log.data.tool}</div>
            <div className="debug-content">
              <pre>{JSON.stringify(log.data.arguments, null, 2)}</pre>
            </div>
          </div>
        );
        
      case 'tool-result':
        return (
          <div className="debug-tool-result">
            <div className="debug-header">工具结果: {log.data.tool}</div>
            <div className="debug-content">
              <pre>{JSON.stringify(log.data.result, null, 2)}</pre>
            </div>
          </div>
        );
        
      case 'complete':
        return (
          <div className="debug-complete">
            <div className="debug-header">完整回复</div>
            <div className="debug-content">{log.data}</div>
          </div>
        );
        
      case 'error':
        return (
          <div className="debug-error">
            <div className="debug-header">错误</div>
            <div className="debug-content">{log.data}</div>
          </div>
        );
        
      default:
        return (
          <div className="debug-unknown">
            <div className="debug-header">{log.type}</div>
            <div className="debug-content">
              <pre>{JSON.stringify(log.data, null, 2)}</pre>
            </div>
          </div>
        );
    }
  };

  // 添加服务器状态检查函数
  const checkServerStatus = async () => {
    try {
      const response = await fetch('http://localhost:5100/api/health');
      return response.ok;
    } catch {
      return false;
    }
  };

  // 在组件加载时检查服务器状态
  useEffect(() => {
    const checkStatus = async () => {
      const isServerUp = await checkServerStatus();
      if (!isServerUp) {
        setMessages([{
          type: 'error',
          content: '无法连接到服务器,请确保后端服务已启动'
        }]);
      }
    };
    checkStatus();
  }, []);

  return (
    <div className={`app-container ${showDebug ? 'with-debug' : ''}`}>
      <div className="chat-container">
        <div className="chat-header">
          <h2>ReAct 智能助手</h2>
          <p className="subtitle">带工具能力的对话机器人</p>
          <button 
            className="debug-toggle-button" 
            onClick={() => setShowDebug(!showDebug)}
          >
            {showDebug ? '关闭调试' : '打开调试'}
          </button>
        </div>
        
        <div 
          className="messages-container" 
          ref={messagesContainerRef}
          onScroll={checkScrollPosition}
        >
          {messages.map((msg, idx) => (
            <div 
              key={`msg-${idx}-${Date.now()}`} 
              className={`message ${msg.type === 'user' ? 'user-message' : 'ai-message'}`}
            >
              <div className="message-content">
                {msg.type === 'user' ? (
                  <p>{msg.content}</p>
                ) : (
                  renderReactContent(msg.content)
                )}
              </div>
            </div>
          ))}
          
          {/* 流式传输中的消息 */}
          {streamingMessage && (
            <div className="message ai-message streaming-message">
              <div className="message-content">
                {renderReactContent(streamingMessage)}
              </div>
            </div>
          )}
          
          {loading && !streamingMessage && (
            <div className="typing-indicator"><span>AI正在思考...</span></div>
          )}
          
          {/* 滚动参考点 */}
          <div ref={messagesEndRef} />
        </div>
        
        {/* 滚动按钮 */}
        {showScrollButton && (
          <button 
            className="scroll-button" 
            onClick={scrollToBottom}
            aria-label="滚动到最新消息"
          >
            <span className="scroll-icon">↓</span>
          </button>
        )}
        
        <div className="input-area">
          <textarea 
            value={input} 
            onChange={(e) => setInput(e.target.value)} 
            onKeyPress={handleKeyPress}
            placeholder="输入你的问题..."
            disabled={loading}
          />
          <button onClick={handleSend} disabled={loading || !input.trim()}>
            {loading ? '发送中...' : '发送'}
          </button>
        </div>
      </div>
      
      {/* 调试面板 - 始终显示当前工具调用和结果 */}
      <div className={`debug-panel ${showDebug ? 'visible' : ''}`}>
        <div className="debug-panel-header">
          <h3>工具调用面板</h3>
          <div className="debug-panel-controls">
            <button onClick={() => setDebugLogs([])} className="clear-logs-button">
              清除记录
            </button>
          </div>
        </div>
        
        {/* 工具活动区域 - 包含当前和历史工具调用 */}
        <div className="tool-activities-container">
          {/* 当前工具调用和结果 */}
          {(currentToolCall || currentToolResult) && (
            <div className="current-tool-section">
              {currentToolCall && (
                <div className="debug-tool-call current-tool">
                  <div className="debug-header">
                    <span>当前工具调用: {currentToolCall.tool}</span>
                    <span className="tool-timestamp">{new Date().toLocaleTimeString()}</span>
                  </div>
                  <div className="debug-content">
                    <pre>{JSON.stringify(currentToolCall.arguments, null, 2)}</pre>
                  </div>
                </div>
              )}
              
              {currentToolResult && (
                <div className="debug-tool-result current-tool">
                  <div className="debug-header">
                    <span>当前工具结果: {currentToolResult.tool}</span>
                    <span className="tool-timestamp">{new Date().toLocaleTimeString()}</span>
                  </div>
                  <div className="debug-content">
                    {formatToolResult(currentToolResult)}
                  </div>
                </div>
              )}
            </div>
          )}
          
          {/* 历史工具调用记录 */}
          {debugLogs.filter(log => log.type === 'tool-call' || log.type === 'tool-result').map((log, index) => (
            <div key={`log-${log.id}-${index}`} className="debug-log-item">
              <div className="debug-timestamp">{log.timestamp}</div>
              {renderDebugLogItem(log)}
            </div>
          ))}
          
          {/* 如果没有任何工具调用记录 */}
          {debugLogs.filter(log => log.type === 'tool-call' || log.type === 'tool-result').length === 0 && 
           !currentToolCall && !currentToolResult && (
            <div className="no-tool-activity">
              暂无工具调用记录
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ChatAgent;
