#!/usr/bin/env python3
"""
从 OpenRouter 网页抓取免费文本到文本模型信息
"""
import asyncio
import json
import os
import re
import sys
from typing import List, Dict, Optional, Tuple, Any
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
from loguru import logger

# 配置常量
CDP_ENDPOINT = "http://localhost:9222"
OPENROUTER_URL = "https://openrouter.ai/models?fmt=table&input_modalities=text&order=newest&output_modalities=text&q=%3Afree"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/models?use_rss=true"
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "openrouter-free-text-to-text.json")
OUTPUT_MODELS_FILE = os.path.join(OUTPUT_DIR, "openrouter-models.json")
PAGE_LOAD_TIMEOUT = 60000
PAGE_LOAD_WAIT_TIME = 5

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<g>{time:YYYY-MM-DD HH:mm:ss}</g> | <level>{level: <8}</level> | {message}",
    level="INFO"
)


async def connect_to_browser(cdp_endpoint: str = CDP_ENDPOINT) -> Tuple[Optional[Playwright], Optional[BrowserContext], Optional[Page]]:
    """
    通过 CDP 连接到本地浏览器
    
    参数:
        cdp_endpoint: CDP 端点地址
        
    返回:
        (playwright, browser_context, page) 元组，如果连接失败则返回 (None, None, None)
    """
    playwright = None
    try:
        logger.info(f"正在通过 CDP 连接到本地浏览器 ({cdp_endpoint})...")
        playwright = await async_playwright().start()
        playwright_instance = await playwright.chromium.connect_over_cdp(cdp_endpoint)
        
        if not playwright_instance.contexts:
            logger.error("浏览器没有可用的上下文")
            if playwright:
                await playwright.stop()
            return None, None, None
        
        browser_context = playwright_instance.contexts[0]
        
        # 获取现有页面或创建新页面
        valid_pages = [p for p in browser_context.pages if not p.is_closed()]
        if valid_pages:
            page = valid_pages[0]
            logger.info(f"使用现有页面，当前 URL: {page.url}")
        else:
            page = await browser_context.new_page()
            logger.info("创建新页面")
        
        page.set_default_timeout(PAGE_LOAD_TIMEOUT)
        return playwright, browser_context, page
        
    except Exception as e:
        logger.error(f"连接浏览器失败: {str(e)}")
        logger.error("请确保浏览器已启动并开启了远程调试端口: chrome --remote-debugging-port=9222")
        if playwright:
            try:
                await playwright.stop()
            except:
                pass
        return None, None, None




async def scrape_openrouter_models() -> List[Dict[str, str]]:
    """
    从 OpenRouter 网页表格中抓取模型信息
    
    返回:
        List[Dict]: 包含模型名称、ID和上下文的列表
    """
    models = []
    playwright = None
    
    try:
        # 连接到浏览器
        playwright, browser_context, page = await connect_to_browser()
        if not playwright or not browser_context or not page:
            logger.error("无法连接到浏览器，退出")
            return []
        
        logger.info(f"正在访问: {OPENROUTER_URL}")
        try:
            await page.goto(OPENROUTER_URL, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
            await asyncio.sleep(PAGE_LOAD_WAIT_TIME)  # 等待页面完全加载
        except Exception as e:
            logger.error(f"访问页面失败: {str(e)}")
            raise
        
        # 等待表格加载
        try:
            await page.wait_for_selector("table tbody tr", timeout=15000)
            logger.debug("找到表格行")
        except Exception as e:
            logger.warning(f"未找到表格: {str(e)}，继续执行...")
        
        # 使用 JavaScript 提取表格中的模型信息
        logger.info("使用 JavaScript 提取表格中的模型信息...")
        js_result = await page.evaluate("""
            () => {
                const models = [];
                const seenModels = new Set();
                
                // 查找表格中的所有数据行（跳过表头）
                const table = document.querySelector('table');
                if (!table) {
                    console.error('未找到表格');
                    return models;
                }
                
                const rows = table.querySelectorAll('tbody tr');
                console.log(`找到 ${rows.length} 行数据`);
                
                rows.forEach((row, idx) => {
                    try {
                        const cells = row.querySelectorAll('td');
                        if (cells.length < 4) {
                            return; // 跳过不完整的行
                        }
                        
                        // 第一列：模型名称和ID
                        const firstCell = cells[0];
                        const nameLink = firstCell.querySelector('a');
                        const codeElement = firstCell.querySelector('code');
                        
                        let modelName = '';
                        let modelId = '';
                        
                        if (nameLink) {
                            modelName = nameLink.innerText?.trim() || nameLink.textContent?.trim() || '';
                        }
                        
                        if (codeElement) {
                            modelId = codeElement.innerText?.trim() || codeElement.textContent?.trim() || '';
                        }
                        
                        // 如果模型名称为空，使用ID
                        if (!modelName && modelId) {
                            modelName = modelId;
                        }
                        
                        // 第四列：上下文信息
                        const contextCell = cells[3];
                        let context = '';
                        
                        if (contextCell) {
                            const contextSpan = contextCell.querySelector('span');
                            if (contextSpan) {
                                context = contextSpan.innerText?.trim() || contextSpan.textContent?.trim() || '';
                                // 移除逗号，转换为纯数字
                                context = context.replace(/,/g, '').trim();
                            }
                        }
                        
                        // 只有当找到模型名称或ID时才添加，并且去重
                        const modelKey = (modelId || modelName).toLowerCase();
                        if (modelKey && !seenModels.has(modelKey)) {
                            seenModels.add(modelKey);
                            models.push({
                                model: modelName || modelId || '',
                                id: modelId || '',
                                context: context || ''
                            });
                        }
                    } catch (e) {
                        console.error(`处理第 ${idx} 行时出错:`, e);
                    }
                });
                
                console.log(`总共提取到 ${models.length} 个模型`);
                return models;
            }
        """)
        
        if js_result:
            # 验证和清理数据
            models = validate_and_clean_models(js_result)
            logger.info(f"通过 JavaScript 提取到 {len(models)} 个有效模型")
        else:
            logger.warning("JavaScript 提取未返回结果")
            return []
        
    except Exception as e:
        logger.error(f"抓取过程中出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []
    finally:
        # 通过 CDP 连接时，只停止 playwright 实例，不关闭浏览器
        if playwright:
            try:
                await playwright.stop()
            except Exception as e:
                logger.warning(f"停止 playwright 时出错: {e}")
    
    logger.info(f"总共提取到 {len(models)} 个模型")
    return models


def validate_and_clean_models(models: List[Dict]) -> List[Dict[str, str]]:
    """
    验证和清理模型数据
    
    参数:
        models: 原始模型数据列表
        
    返回:
        清理后的模型数据列表
    """
    validated_models = []
    seen_models = set()
    
    for model in models:
        if not isinstance(model, dict):
            continue
        
        model_name = model.get("model", "").strip()
        model_id = model.get("id", "").strip()
        
        # 至少需要有模型名称或ID
        if not model_name and not model_id:
            continue
        
        # 使用ID作为唯一标识，如果没有ID则使用名称
        model_key = (model_id or model_name).lower()
        if not model_key or model_key in seen_models:
            continue
        seen_models.add(model_key)
        
        # 清理上下文信息（移除非数字字符，只保留数字）
        context = str(model.get("context", "")).strip()
        if context:
            # 提取数字部分
            context_match = re.search(r'(\d+)', context)
            if context_match:
                context = context_match.group(1)
            else:
                context = ""
        
        validated_models.append({
            "model": model_name or model_id,
            "id": model_id,
            "context": context
        })
    
    return validated_models


async def fetch_openrouter_api_models() -> Dict[str, Any]:
    """
    从 OpenRouter API 获取模型列表并保存到文件
    
    返回:
        API 返回的 JSON 数据
    """
    playwright = None
    
    try:
        # 连接到浏览器
        playwright, browser_context, page = await connect_to_browser()
        if not playwright or not browser_context or not page:
            logger.error("无法连接到浏览器，退出")
            return {}
        
        logger.info(f"正在访问 API: {OPENROUTER_API_URL}")
        try:
            await page.goto(OPENROUTER_API_URL, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT)
            await asyncio.sleep(2)  # 等待页面完全加载
        except Exception as e:
            logger.error(f"访问 API 页面失败: {str(e)}")
            raise
        
        # 获取页面内容（API 返回的 JSON）
        content = await page.evaluate("() => document.body.innerText || document.body.textContent")
        
        if not content:
            logger.error("未获取到 API 响应内容")
            return {}
        
        # 解析 JSON
        try:
            api_data = json.loads(content)
            logger.info(f"成功获取 API 数据")
            return api_data
        except json.JSONDecodeError as e:
            logger.error(f"解析 API JSON 响应失败: {str(e)}")
            return {}
        
    except Exception as e:
        logger.error(f"获取 API 数据过程中出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {}
    finally:
        if playwright:
            try:
                await playwright.stop()
            except Exception as e:
                logger.warning(f"停止 playwright 时出错: {e}")


async def main():
    """主函数"""
    try:
        logger.info("=" * 60)
        logger.info("开始抓取 OpenRouter 免费文本到文本模型信息")
        logger.info("=" * 60)
        
        models = await scrape_openrouter_models()
        
        if not models:
            logger.warning("未提取到任何模型信息")
            sys.exit(1)
        
        # 保存到 JSON 文件
        try:
            # 确保输出目录存在
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(models, f, ensure_ascii=False, indent=2)
            logger.success(f"成功保存 {len(models)} 个模型信息到 {OUTPUT_FILE}")
        except Exception as e:
            logger.error(f"保存文件失败: {str(e)}")
            sys.exit(1)
        
        # 打印统计信息
        logger.info("\n" + "=" * 60)
        logger.info("抓取统计:")
        logger.info(f"  总模型数: {len(models)}")
        models_with_id = sum(1 for m in models if m.get("id"))
        models_with_context = sum(1 for m in models if m.get("context"))
        logger.info(f"  有ID的模型: {models_with_id}")
        logger.info(f"  有上下文信息的模型: {models_with_context}")
        logger.info("=" * 60)
        
        # 打印前几个模型作为示例
        if models:
            logger.info("\n前3个模型示例:")
            for i, model in enumerate(models[:3], 1):
                logger.info(f"\n{i}. 模型名称: {model.get('model', 'N/A')}")
                model_id = model.get('id', '')
                if model_id:
                    logger.info(f"   模型ID: {model_id}")
                context = model.get('context', '')
                if context:
                    logger.info(f"   上下文 (tokens): {context}")
        
        # 获取 OpenRouter API 模型列表
        logger.info("\n" + "=" * 60)
        logger.info("开始获取 OpenRouter API 模型列表")
        logger.info("=" * 60)
        
        api_models = await fetch_openrouter_api_models()
        
        if api_models:
            try:
                with open(OUTPUT_MODELS_FILE, "w", encoding="utf-8") as f:
                    json.dump(api_models, f, ensure_ascii=False, indent=2)
                
                # 统计模型数量
                data_list = api_models.get("data", [])
                logger.success(f"成功保存 API 模型数据到 {OUTPUT_MODELS_FILE}")
                logger.info(f"  API 返回模型数: {len(data_list)}")
            except Exception as e:
                logger.error(f"保存 API 模型文件失败: {str(e)}")
        else:
            logger.warning("未获取到 API 模型数据")
        
    except KeyboardInterrupt:
        logger.warning("\n用户中断程序")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序执行失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
