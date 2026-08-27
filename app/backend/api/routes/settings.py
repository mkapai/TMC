#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统设置API路由

管理系统配置
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from log_manager import get_logger
from pathlib import Path

logger = get_logger('api.settings', 'api.log')

router = APIRouter()


@router.get("")
async def get_settings():
    """
    获取系统设置
    
    返回当前的系统配置
    """
    try:
        logger.info("📋 获取系统设置")
        from config import Config
        
        # 返回当前配置
        settings = {
            "api_id": getattr(Config, 'API_ID', ''),
            "api_hash": getattr(Config, 'API_HASH', ''),
            "bot_token": getattr(Config, 'BOT_TOKEN', ''),
            "phone_number": getattr(Config, 'PHONE_NUMBER', ''),
            "admin_user_ids": getattr(Config, 'ADMIN_USER_IDS', ''),
            "enable_proxy": getattr(Config, 'ENABLE_PROXY', False),
            "proxy_type": getattr(Config, 'PROXY_TYPE', 'http'),
            "proxy_host": getattr(Config, 'PROXY_HOST', '127.0.0.1'),
            "proxy_port": getattr(Config, 'PROXY_PORT', '7890'),
            "proxy_username": getattr(Config, 'PROXY_USERNAME', ''),
            "proxy_password": "***" if getattr(Config, 'PROXY_PASSWORD', '') else '',
            "enable_log_cleanup": getattr(Config, 'ENABLE_LOG_CLEANUP', False),
            "log_retention_days": getattr(Config, 'LOG_RETENTION_DAYS', '30'),
            "log_cleanup_time": getattr(Config, 'LOG_CLEANUP_TIME', '02:00'),
            "max_log_size": getattr(Config, 'MAX_LOG_SIZE', '100'),
            "public_base_url": getattr(Config, 'PUBLIC_BASE_URL', ''),
            "resource_cache_max_gb": getattr(Config, 'RESOURCE_CACHE_MAX_GB', 100),
            "public_resource_ttl_days": getattr(Config, 'PUBLIC_RESOURCE_TTL_DAYS', 7),
        }
        
        logger.info("✅ 系统设置获取成功")
        return JSONResponse(content={
            "success": True,
            "config": settings
        })
    except Exception as e:
        logger.error(f"❌ 获取设置失败: {e}")
        return JSONResponse(content={
            "success": False,
            "message": f"获取设置失败: {str(e)}"
        }, status_code=500)


@router.post("")
async def save_settings(request: Request):
    """
    保存系统设置
    
    更新 config/app.config 文件并重新加载配置
    """
    try:
        data = await request.json()
        logger.info("💾 开始保存系统设置...")
        
        # 记录主要配置项的变更
        config_changes = []
        if data.get('api_id'):
            config_changes.append(f"API_ID: {'已设置' if data.get('api_id') else '未设置'}")
        if data.get('phone_number'):
            config_changes.append(f"Phone: {data.get('phone_number')}")
        if data.get('enable_proxy'):
            proxy_info = f"{data.get('proxy_type', 'http')}://{data.get('proxy_host', '127.0.0.1')}:{data.get('proxy_port', '7890')}"
            config_changes.append(f"代理: {proxy_info}")
        else:
            config_changes.append("代理: 已禁用")
        
        logger.info(f"📝 配置变更: {', '.join(config_changes)}")
        
        if 'public_base_url' in data:
            public_base_url = str(data.get('public_base_url') or '').strip().rstrip('/')
            if public_base_url and not public_base_url.lower().startswith(("http://", "https://")):
                return JSONResponse(
                    content={"success": False, "message": "公开访问地址必须使用 http:// 或 https://"},
                    status_code=400,
                )
            data['public_base_url'] = public_base_url
        if 'resource_cache_max_gb' in data:
            try:
                if float(data['resource_cache_max_gb']) <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return JSONResponse(
                    content={"success": False, "message": "缓存容量必须大于 0 GB"},
                    status_code=400,
                )
        if 'public_resource_ttl_days' in data:
            try:
                ttl_days = int(data['public_resource_ttl_days'])
                if ttl_days < 1 or ttl_days > 3650:
                    raise ValueError
            except (TypeError, ValueError):
                return JSONResponse(
                    content={"success": False, "message": "公开资源有效期必须为 1 至 3650 天"},
                    status_code=400,
                )
            data['public_resource_ttl_days'] = ttl_days

        key_map = {
            'api_id': 'API_ID', 'api_hash': 'API_HASH', 'bot_token': 'BOT_TOKEN',
            'phone_number': 'PHONE_NUMBER', 'admin_user_ids': 'ADMIN_USER_IDS',
            'enable_proxy': 'ENABLE_PROXY', 'proxy_type': 'PROXY_TYPE',
            'proxy_host': 'PROXY_HOST', 'proxy_port': 'PROXY_PORT',
            'proxy_username': 'PROXY_USERNAME', 'proxy_password': 'PROXY_PASSWORD',
            'enable_log_cleanup': 'ENABLE_LOG_CLEANUP',
            'log_retention_days': 'LOG_RETENTION_DAYS',
            'log_cleanup_time': 'LOG_CLEANUP_TIME', 'max_log_size': 'MAX_LOG_SIZE',
            'public_base_url': 'PUBLIC_BASE_URL',
            'resource_cache_max_gb': 'RESOURCE_CACHE_MAX_GB',
            'public_resource_ttl_days': 'PUBLIC_RESOURCE_TTL_DAYS',
        }
        updates = {}
        for request_key, config_key in key_map.items():
            if request_key not in data:
                continue
            value = data[request_key]
            if request_key == 'proxy_password' and value in ('', '***'):
                continue
            if isinstance(value, bool):
                value = str(value).lower()
            updates[config_key] = str(value)

        from config import PROJECT_ROOT

        config_dir = PROJECT_ROOT / 'config'
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / 'app.config'
        lines = config_file.read_text(encoding='utf-8').splitlines() if config_file.exists() else []
        seen = set()
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                continue
            key = stripped.split('=', 1)[0].strip()
            if key in updates:
                lines[index] = f"{key}={updates[key]}"
                seen.add(key)
        if updates.keys() - seen:
            if lines and lines[-1]:
                lines.append('')
            lines.append('# 消息投递配置')
            lines.extend(f"{key}={updates[key]}" for key in updates.keys() - seen)
        config_file.write_text("\n".join(lines) + "\n", encoding='utf-8')
        
        logger.info(f"💾 配置已保存到: {config_file}")
        
        # 重新加载配置
        from config import Config
        Config.reload()
        
        # 重新加载代理管理器（重要！确保代理配置立即生效）
        from proxy_utils import reload_proxy_manager
        reload_proxy_manager()
        
        logger.info("🔄 配置重新加载完成（包括代理管理器）")
        logger.info("✅ 系统配置保存成功！代理配置已生效，新启动的客户端将使用新配置")
        
        # 检查是否有代理配置变更
        proxy_changed = any(key in data for key in ('enable_proxy', 'proxy_host', 'proxy_port'))
        
        return JSONResponse(content={
            "success": True,
            "message": "设置保存成功！代理配置已更新，请重启已运行的客户端以使其生效。" if proxy_changed else "设置保存成功！",
            "requires_client_restart": proxy_changed
        })
    except Exception as e:
        logger.error(f"❌ 保存设置失败: {e}", exc_info=True)
        return JSONResponse(content={
            "success": False,
            "message": f"保存设置失败: {str(e)}"
        }, status_code=500)


@router.post("/test-proxy")
async def test_proxy(request: Request):
    """
    测试代理连接
    
    从请求中获取代理配置并测试连接性
    """
    try:
        data = await request.json()
        logger.info(f"🧪 测试代理连接: {data.get('proxy_type', 'http')}://{data.get('proxy_host', '127.0.0.1')}:{data.get('proxy_port', '7890')}")
        
        # 验证必需参数
        if not data.get('enable_proxy'):
            return JSONResponse(content={
                "success": False,
                "message": "代理未启用"
            }, status_code=400)
        
        proxy_host = data.get('proxy_host')
        proxy_port = data.get('proxy_port')
        
        if not proxy_host or not proxy_port:
            return JSONResponse(content={
                "success": False,
                "message": "代理配置不完整：缺少主机或端口"
            }, status_code=400)
        
        # 测试代理连接到Telegram
        import socket
        import time
        import httpx
        from proxy_utils import get_proxy_manager
        
        try:
            # 第1步: 测试TCP连接到代理服务器
            logger.info(f"🔌 步骤1: 测试代理服务器连接 {proxy_host}:{proxy_port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            
            start_time = time.time()
            tcp_result = sock.connect_ex((proxy_host, int(proxy_port)))
            tcp_time = time.time()
            sock.close()
            
            tcp_latency_ms = (tcp_time - start_time) * 1000
            
            if tcp_result != 0:
                error_codes = {
                    10061: "连接被拒绝 (目标端口未开放)",
                    10060: "连接超时 (目标主机无响应)",
                    10051: "网络不可达",
                    10065: "主机不可达"
                }
                error_msg = error_codes.get(tcp_result, f"连接失败 (错误码: {tcp_result})")
                logger.warning(f"❌ 代理TCP连接失败: {error_msg}")
                message = (
                    f"❌ 代理连接失败\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📡 代理信息\n"
                    f"  • 主机: {proxy_host}\n"
                    f"  • 端口: {proxy_port}\n"
                    f"  • 错误: {error_msg}\n\n"
                    f"💡 请检查\n"
                    f"  1. 代理服务器是否运行\n"
                    f"  2. IP和端口是否正确\n"
                    f"  3. 防火墙设置\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                return JSONResponse(content={
                    "success": False,
                    "message": message
                }, status_code=400)
            
            logger.info(f"✅ TCP连接成功, 延迟: {tcp_latency_ms:.0f}ms")
            
            # 第2步: 通过代理访问Telegram网站
            logger.info(f"🌐 步骤2: 通过代理访问Telegram网站...")
            
            try:
                # 构建代理URL
                proxy_type = data.get('proxy_type', 'http').lower()
                proxy_username = data.get('proxy_username', '')
                proxy_password = data.get('proxy_password', '')
                
                # 构建代理认证信息
                if proxy_username and proxy_password:
                    proxy_url = f"{proxy_type}://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
                else:
                    proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
                
                # 测试访问Telegram网站
                test_url = "https://telegram.org"
                
                async with httpx.AsyncClient(
                    proxies=proxy_url,
                    timeout=10.0,
                    follow_redirects=True
                ) as client:
                    tg_start_time = time.time()
                    response = await client.get(test_url)
                    tg_end_time = time.time()
                    
                    tg_latency_ms = (tg_end_time - tg_start_time) * 1000
                    
                    if response.status_code == 200:
                        # 成功访问Telegram
                        total_latency = tcp_latency_ms + tg_latency_ms
                        
                        # 根据总延迟给出评价
                        if total_latency < 500:
                            speed_rating = "极快 🚀"
                        elif total_latency < 1000:
                            speed_rating = "很快 ✨"
                        elif total_latency < 2000:
                            speed_rating = "良好 ✅"
                        elif total_latency < 5000:
                            speed_rating = "一般 ⚠️"
                        else:
                            speed_rating = "较慢 🐢"
                        
                        logger.info(f"✅ Telegram访问成功: {response.status_code}, 延迟: {tg_latency_ms:.0f}ms")
                        
                        # 格式化消息
                        message = (
                            f"🎉 代理测试成功\n\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"📡 代理信息\n"
                            f"  • 主机: {proxy_host}\n"
                            f"  • 端口: {proxy_port}\n"
                            f"  • 类型: {proxy_type.upper()}\n\n"
                            f"⚡ 性能指标\n"
                            f"  • TCP连接: {tcp_latency_ms:.0f}ms\n"
                            f"  • Telegram: {tg_latency_ms:.0f}ms\n"
                            f"  • 总延迟: {total_latency:.0f}ms {speed_rating}\n"
                            f"━━━━━━━━━━━━━━━━━━\n\n"
                            f"✅ 可以正常访问Telegram"
                        )
                        
                        return JSONResponse(content={
                            "success": True,
                            "message": message,
                            "latency_ms": round(total_latency, 2),
                            "tcp_latency_ms": round(tcp_latency_ms, 2),
                            "tg_latency_ms": round(tg_latency_ms, 2)
                        })
                    else:
                        logger.warning(f"⚠️ Telegram访问HTTP错误: {response.status_code}")
                        message = (
                            f"⚠️ 代理连接成功，但无法访问Telegram\n\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"📊 测试结果\n"
                            f"  • TCP连接: ✅ 成功 ({tcp_latency_ms:.0f}ms)\n"
                            f"  • HTTP状态: ❌ {response.status_code}\n\n"
                            f"💡 可能原因\n"
                            f"  1. 代理不支持HTTPS\n"
                            f"  2. 代理限制了Telegram访问\n"
                            f"  3. 网络环境问题\n"
                            f"━━━━━━━━━━━━━━━━━━"
                        )
                        return JSONResponse(content={
                            "success": False,
                            "message": message
                        }, status_code=400)
                        
            except httpx.ProxyError as proxy_err:
                logger.error(f"❌ 代理协议错误: {proxy_err}")
                message = (
                    f"❌ 代理配置错误\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 测试结果\n"
                    f"  • TCP连接: ✅ 成功 ({tcp_latency_ms:.0f}ms)\n"
                    f"  • Telegram: ❌ 失败\n\n"
                    f"💡 可能原因\n"
                    f"  1. 代理类型选择错误\n"
                    f"  2. 需要用户名密码认证\n"
                    f"  3. 代理协议不兼容\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🔍 错误详情: {str(proxy_err)}"
                )
                return JSONResponse(content={
                    "success": False,
                    "message": message
                }, status_code=400)
                
            except httpx.TimeoutException:
                logger.error(f"❌ Telegram访问超时")
                message = (
                    f"⏱️ 访问Telegram超时\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 测试结果\n"
                    f"  • TCP连接: ✅ 成功 ({tcp_latency_ms:.0f}ms)\n"
                    f"  • Telegram: ❌ 超时 (>10秒)\n\n"
                    f"💡 可能原因\n"
                    f"  1. 代理速度太慢\n"
                    f"  2. 代理不稳定\n"
                    f"  3. 网络环境差\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                return JSONResponse(content={
                    "success": False,
                    "message": message
                }, status_code=400)
                
            except Exception as http_err:
                logger.error(f"❌ HTTP请求异常: {http_err}")
                message = (
                    f"❌ 代理测试失败\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 测试结果\n"
                    f"  • TCP连接: ✅ 成功 ({tcp_latency_ms:.0f}ms)\n"
                    f"  • Telegram: ❌ 失败\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🔍 错误详情: {str(http_err)}"
                )
                return JSONResponse(content={
                    "success": False,
                    "message": message
                }, status_code=400)
                
        except socket.gaierror as e:
            logger.error(f"❌ DNS解析失败: {e}")
            message = (
                f"❌ 无法解析主机名\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📡 代理信息\n"
                f"  • 主机: {proxy_host}\n"
                f"  • 错误: DNS解析失败\n\n"
                f"💡 请检查\n"
                f"  • 主机名拼写是否正确\n"
                f"  • 网络DNS设置\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            return JSONResponse(content={
                "success": False,
                "message": message
            }, status_code=400)
            
        except ValueError as e:
            logger.error(f"❌ 端口格式错误: {e}")
            message = (
                f"❌ 端口格式错误\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📡 代理信息\n"
                f"  • 端口: {proxy_port}\n"
                f"  • 错误: 端口格式无效\n\n"
                f"💡 要求\n"
                f"  • 必须是数字\n"
                f"  • 范围: 1-65535\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            return JSONResponse(content={
                "success": False,
                "message": message
            }, status_code=400)
            
        except Exception as e:
            logger.error(f"❌ 代理连接测试异常: {e}")
            message = (
                f"❌ 测试失败\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🔍 错误详情\n"
                f"  {str(e)}\n"
                f"━━━━━━━━━━━━━━━━━━"
            )
            return JSONResponse(content={
                "success": False,
                "message": message
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"❌ 测试代理失败: {e}", exc_info=True)
        message = (
            f"❌ 系统错误\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔍 错误详情\n"
            f"  {str(e)}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        return JSONResponse(content={
            "success": False,
            "message": message
        }, status_code=500)


"""
✅ 所有3个端点已完成!

- GET /api/settings - 获取系统设置
- POST /api/settings - 保存系统设置
- POST /api/settings/test-proxy - 测试代理连接
"""
