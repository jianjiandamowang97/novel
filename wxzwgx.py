import asyncio
import aiohttp
from aiohttp import ClientSession, ClientTimeout, TCPConnector
from bs4 import BeautifulSoup
import time
import logging
from typing import Optional, List, Tuple, Dict, Set
from urllib.parse import urljoin, urlparse, parse_qs
import re
from datetime import datetime
from pathlib import Path
import random
import socket
import ssl


class FastNovelCrawler:
    """高速小说爬虫类，支持异步并发爬取 - 分页顺序修复版本"""

    def __init__(self, base_url: str = 'https://www.twinfoo.com',
                 concurrent_limit: int = 2, base_delay: float = 1.5):
        """
        初始化爬虫

        Args:
            base_url: 基础URL
            concurrent_limit: 并发连接数限制（降低到2）
            base_delay: 基础延迟时间（增加到1.5秒）
        """
        self.base_url = base_url
        self.concurrent_limit = concurrent_limit
        self.base_delay = base_delay
        self.chapter_count = 0
        self.total_words = 0
        self.failed_urls: Set[str] = set()
        self.retry_count = 5  # 增加重试次数

        # 响应时间监控
        self.response_times = []
        self.server_load_factor = 1.0

        # 设置日志
        self._setup_logging()

        # 更新请求头，添加更多字段
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }

    def _setup_logging(self) -> None:
        """设置日志配置"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('fast_novel_crawler.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def check_domain_availability(self) -> bool:
        """检查域名可用性"""
        try:
            parsed_url = urlparse(self.base_url)
            host = parsed_url.hostname
            socket.gethostbyname(host)
            self.logger.info(f"域名解析成功: {host}")
            return True
        except socket.gaierror as e:
            self.logger.error(f"域名解析失败: {e}")
            self.logger.info("建议检查:")
            self.logger.info("1. 网络连接是否正常")
            self.logger.info("2. DNS设置是否正确")
            self.logger.info("3. 域名是否仍然有效")
            return False

    async def diagnose_network_issue(self) -> None:
        """诊断网络问题"""
        self.logger.info("开始网络诊断...")

        # 解析URL
        parsed_url = urlparse(self.base_url)
        host = parsed_url.hostname
        port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)

        # 1. DNS解析测试
        try:
            ip = socket.gethostbyname(host)
            self.logger.info(f"✅ DNS解析成功: {host} -> {ip}")
        except socket.gaierror as e:
            self.logger.error(f"❌ DNS解析失败: {e}")
            return

        # 2. 端口连通性测试
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                self.logger.info(f"✅ 端口 {port} 连通")
            else:
                self.logger.error(f"❌ 端口 {port} 不通")
                return
        except Exception as e:
            self.logger.error(f"❌ 端口测试失败: {e}")
            return

        # 3. HTTP请求测试
        try:
            async with await self.create_session() as session:
                async with session.get(self.base_url, timeout=30) as response:
                    self.logger.info(f"✅ HTTP请求成功: {response.status}")
        except Exception as e:
            self.logger.error(f"❌ HTTP请求失败: {e}")

    def _calculate_adaptive_delay(self) -> float:
        """计算自适应延迟时间 - 修复版本"""
        if not self.response_times:
            return self.base_delay * 2  # 增加基础延迟

        # 计算平均响应时间
        avg_response_time = sum(self.response_times[-10:]) / len(self.response_times[-10:])

        # 根据响应时间调整延迟 - 更保守的策略
        if avg_response_time > 5.0:  # 服务器很慢
            self.server_load_factor = 3.0
        elif avg_response_time > 3.0:  # 服务器较慢
            self.server_load_factor = 2.5
        elif avg_response_time > 1.5:  # 服务器中等负载
            self.server_load_factor = 2.0
        else:  # 服务器响应快
            self.server_load_factor = 1.5  # 即使快也保持谨慎

        # 添加随机性，避免规律性请求
        base_delay = self.base_delay * self.server_load_factor
        random_factor = random.uniform(1.0, 2.0)  # 增加随机范围

        return base_delay * random_factor

    async def create_session(self) -> ClientSession:
        """创建异步HTTP会话 - 修复版本"""
        # 创建更宽松的SSL上下文
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # 增加超时时间
        timeout = ClientTimeout(total=60, connect=20, sock_read=30)

        connector = TCPConnector(
            limit=self.concurrent_limit * 2,
            limit_per_host=self.concurrent_limit,
            keepalive_timeout=60,
            enable_cleanup_closed=True,
            ssl=ssl_context,  # 使用自定义SSL上下文
            family=socket.AF_INET,  # 强制使用IPv4
            resolver=None,
            use_dns_cache=True,
            ttl_dns_cache=300,
        )

        return ClientSession(
            timeout=timeout,
            connector=connector,
            headers=self.headers,
            trust_env=True,  # 信任环境变量中的代理设置
        )

    def _clean_text(self, text: str) -> str:
        """清理文本内容"""
        if not text:
            return ""

        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text.strip())

        # 移除常见的广告文字
        ad_patterns = [
            r'本站.*?提醒您.*?',
            r'请收藏.*?',
            r'手机用户.*?',
            r'记住.*?网址.*?',
            r'最新章节.*?',
            r'无弹窗.*?',
            r'.*?首发.*?',
            r'.*?更新最快.*?',
        ]

        for pattern in ad_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        return text.strip()

    async def fetch_with_retry(self, session: ClientSession, url: str) -> Optional[str]:
        """带重试的HTTP请求 - 修复版本"""
        for attempt in range(self.retry_count):
            try:
                start_time = time.time()

                # 添加更多的错误处理
                async with session.get(url, allow_redirects=True) as response:
                    if response.status == 200:
                        content = await response.text()
                        response_time = time.time() - start_time
                        self.response_times.append(response_time)

                        if len(self.response_times) > 50:
                            self.response_times = self.response_times[-50:]

                        return content
                    elif response.status == 403:
                        self.logger.warning(f"访问被拒绝 403: {url}")
                        await asyncio.sleep(5)  # 等待更长时间
                    elif response.status == 404:
                        self.logger.warning(f"页面不存在 404: {url}")
                        break  # 404不需要重试
                    else:
                        self.logger.warning(f"HTTP {response.status}: {url}")

            except aiohttp.ClientConnectorError as e:
                self.logger.warning(f"连接错误 (尝试 {attempt + 1}/{self.retry_count}): {e}")
                # 连接错误时等待更长时间
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(5 * (attempt + 1))
            except aiohttp.ClientSSLError as e:
                self.logger.warning(f"SSL错误 (尝试 {attempt + 1}/{self.retry_count}): {e}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(3 * (attempt + 1))
            except asyncio.TimeoutError:
                self.logger.warning(f"请求超时 (尝试 {attempt + 1}/{self.retry_count}): {url}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(2 * (attempt + 1))
            except Exception as e:
                self.logger.warning(f"未知错误 (尝试 {attempt + 1}/{self.retry_count}): {e}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(2 ** attempt)

        self.failed_urls.add(url)
        return None

    async def extract_page_content(self, session: ClientSession, url: str) -> Tuple[
        List[str], Optional[str], Optional[str]]:
        """
        异步提取页面内容

        Returns:
            元组包含:
            - 页面内容段落列表
            - 下一章链接(仅在主页面返回)
            - 章节标题(仅在主页面返回)
        """
        html_content = await self.fetch_with_retry(session, url)
        if not html_content:
            return [], None, None

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # 提取标题（仅主页面）
            chapter_title = None
            title_selectors = [
                'h1', 'h2', '.title', '.chapter-title',
                '.post-title', '.entry-title', 'title'
            ]

            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title = self._clean_text(title_element.get_text())
                    if title and len(title) > 0:
                        chapter_title = title
                        break

            # 查找包含文章内容的div
            article_div = soup.find('div', class_='blurstxt')
            if not article_div:
                return [], None, chapter_title

            # 提取所有段落
            paragraphs = article_div.find_all('p')
            if not paragraphs:
                return [], None, chapter_title

            # 提取并清理文本内容
            content_list = []
            for p_tag in paragraphs:
                text = self._clean_text(p_tag.get_text())
                if text and len(text) > 5:
                    content_list.append(text)

            # 查找下一章链接
            next_chapter_url = None
            next_link = soup.find('a', rel='next')
            if next_link:
                next_chapter_url = next_link.get('href')
                if next_chapter_url and not next_chapter_url.startswith('http'):
                    next_chapter_url = urljoin(self.base_url, next_chapter_url)

            return content_list, next_chapter_url, chapter_title

        except Exception as e:
            self.logger.error(f"内容提取失败: {e}, URL: {url}")
            return [], None, None

    def _extract_page_number(self, url: str) -> int:
        """从URL中提取页码 - 新增方法"""
        try:
            # 方法1: 从URL路径中提取页码
            # 例如: /page/2/, /2.html, /p2.html
            path_patterns = [
                r'/page/(\d+)/?',
                r'/(\d+)\.html?',
                r'/p(\d+)\.html?',
                r'page=(\d+)',
                r'p=(\d+)',
            ]

            for pattern in path_patterns:
                match = re.search(pattern, url)
                if match:
                    return int(match.group(1))

            # 方法2: 从查询参数中提取
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)

            for param in ['page', 'p', 'paged']:
                if param in query_params:
                    try:
                        return int(query_params[param][0])
                    except (ValueError, IndexError):
                        continue

            # 方法3: 从fragment中提取
            if parsed_url.fragment:
                match = re.search(r'(\d+)', parsed_url.fragment)
                if match:
                    return int(match.group(1))

            # 如果都无法提取，返回默认值
            return 0

        except Exception as e:
            self.logger.warning(f"页码提取失败: {url}, 错误: {e}")
            return 0

    def _sort_pagination_urls(self, urls: List[str]) -> List[str]:
        """对分页URL进行智能排序 - 新增方法"""
        try:
            # 为每个URL分配页码
            url_with_pages = []
            for url in urls:
                page_num = self._extract_page_number(url)
                url_with_pages.append((page_num, url))

            # 按页码排序
            url_with_pages.sort(key=lambda x: x[0])

            # 返回排序后的URL列表
            sorted_urls = [url for page_num, url in url_with_pages]

            self.logger.info(f"分页URL排序完成: {len(sorted_urls)} 个页面")
            for i, (page_num, url) in enumerate(url_with_pages):
                self.logger.debug(f"  页面 {i + 1}: 页码 {page_num}, URL: {url}")

            return sorted_urls

        except Exception as e:
            self.logger.error(f"分页URL排序失败: {e}")
            return urls  # 如果排序失败，返回原始列表

    def _deduplicate_preserve_order(self, urls: List[str]) -> List[str]:
        """去重但保持顺序 - 新增方法"""
        seen = set()
        result = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                result.append(url)
        return result

    async def get_pagination_links(self, session: ClientSession, url: str) -> List[str]:
        """异步获取分页链接 - 修复版本"""
        html_content = await self.fetch_with_retry(session, url)
        if not html_content:
            return []

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            pagination_urls = []

            # 扩展分页链接查找策略
            pagination_selectors = [
                # 原有的选择器
                'a.post-page-numbers',
                # 额外的常见分页选择器
                'a[class*="page"]',
                'a[href*="page"]',
                'a[href*="/p"]',
                '.pagination a',
                '.page-numbers a',
                '.wp-pagenavi a',
                '.pagenavi a',
            ]

            # 尝试多种选择器
            for selector in pagination_selectors:
                page_links = soup.select(selector)
                for link in page_links:
                    href = link.get('href')
                    if href:
                        # 过滤掉"上一页"、"下一页"等导航链接
                        link_text = link.get_text().strip().lower()
                        if any(nav_text in link_text for nav_text in ['prev', 'next', '上一', '下一', '首页', '末页']):
                            continue

                        if not href.startswith('http'):
                            href = urljoin(self.base_url, href)
                        if self._validate_url(href) and href != url:  # 排除当前页面
                            pagination_urls.append(href)

            # 去重但保持原始顺序
            pagination_urls = self._deduplicate_preserve_order(pagination_urls)

            # 智能排序
            if pagination_urls:
                pagination_urls = self._sort_pagination_urls(pagination_urls)
                self.logger.info(f"找到并排序了 {len(pagination_urls)} 个分页链接")

            return pagination_urls

        except Exception as e:
            self.logger.error(f"分页链接提取失败: {e}")
            return []

    def _validate_url(self, url: str) -> bool:
        """验证URL格式"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    async def crawl_complete_chapter_async(self, session: ClientSession, chapter_url: str, chapter_num: int) -> Tuple[
        Optional[str], List[str], Optional[str]]:
        """
        异步爬取完整章节内容（包括所有分页）- 修复版本

        Returns:
            元组包含:
            - 章节标题
            - 完整章节内容
            - 下一章链接
        """
        print(f"📖 开始爬取第{chapter_num}章: {chapter_url}")

        # 并发爬取主页面和分页链接
        main_task = self.extract_page_content(session, chapter_url)
        pagination_task = self.get_pagination_links(session, chapter_url)

        # 等待主页面和分页链接获取完成
        main_result, pagination_result = await asyncio.gather(
            main_task, pagination_task, return_exceptions=True
        )

        # 处理主页面结果
        if isinstance(main_result, Exception):
            self.logger.error(f"主页面爬取失败: {main_result}")
            return None, [], None

        main_content, next_chapter_url, chapter_title = main_result

        # 处理分页结果
        if isinstance(pagination_result, Exception):
            self.logger.warning(f"分页链接获取失败: {pagination_result}")
            pagination_links = []
        else:
            pagination_links = pagination_result

        all_content = main_content.copy()

        if pagination_links:
            print(f"   📄 发现 {len(pagination_links)} 个分页，按顺序爬取中...")

            # 创建分页爬取任务 - 改为按顺序处理
            page_contents = []
            successful_pages = 0

            # 方法1: 顺序爬取（保证顺序）
            for i, page_url in enumerate(pagination_links):
                try:
                    page_content, _, _ = await self.extract_page_content(session, page_url)
                    if page_content:
                        page_contents.append((i, page_content))  # 保存索引和内容
                        successful_pages += 1
                        print(f"     ✅ 分页 {i + 1}/{len(pagination_links)} 完成")
                    else:
                        print(f"     ❌ 分页 {i + 1}/{len(pagination_links)} 内容为空")

                    # 分页间添加小延迟
                    if i < len(pagination_links) - 1:
                        await asyncio.sleep(0.5)

                except Exception as e:
                    self.logger.warning(f"分页 {i + 1} 爬取失败: {e}")
                    continue

            # 按索引顺序添加分页内容
            page_contents.sort(key=lambda x: x[0])  # 按索引排序
            for _, page_content in page_contents:
                all_content.extend(page_content)

            print(f"   ✅ 分页完成，成功爬取 {successful_pages}/{len(pagination_links)} 个分页")
        else:
            print("   📄 本章节无分页")

        total_words = sum(len(p) for p in all_content)
        print(f"   📊 第{chapter_num}章完成，总段落: {len(all_content)}，总字数: {total_words:,}")

        # 自适应延迟
        delay = self._calculate_adaptive_delay()
        await asyncio.sleep(delay)

        return chapter_title, all_content, next_chapter_url

    def format_chapter_content(self, title: str, all_content: List[str], chapter_num: int) -> str:
        """格式化章节内容"""
        formatted_content = []

        separator = "=" * 80
        formatted_content.append(separator)

        if title:
            display_title = title if len(title) <= 60 else title[:57] + "..."
            formatted_content.append(f"{display_title:^80}")
        else:
            formatted_content.append(f"第{chapter_num}章".center(80))

        formatted_content.append(separator)
        formatted_content.append("")

        for i, paragraph in enumerate(all_content):
            formatted_paragraph = f"    {paragraph}"
            formatted_content.append(formatted_paragraph)

            if i < len(all_content) - 1:
                formatted_content.append("")

        formatted_content.append("")
        formatted_content.append("")

        return "\n".join(formatted_content)

    async def save_chapter_to_file_async(self, chapter_content: str, output_file: str) -> bool:
        """异步保存章节到文件"""
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 使用异步文件写入
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_file_sync, chapter_content, output_file)

            return True

        except Exception as e:
            self.logger.error(f"文件保存失败: {e}")
            return False

    def _write_file_sync(self, content: str, filename: str):
        """同步文件写入（在线程池中执行）"""
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(content)

    async def crawl_novel_from_chapter_async(self, start_url: str, output_file: str = None) -> bool:
        """异步爬取小说 - 修复版本"""
        # 首先检查域名可用性
        if not self.check_domain_availability():
            self.logger.error("域名不可用，无法继续爬取")
            return False

        # 进行网络诊断
        await self.diagnose_network_issue()

        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"小说_{timestamp}.txt"

        # 初始化输出文件
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"小说爬取开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"起始章节: {start_url}\n")
                f.write(f"并发限制: {self.concurrent_limit} | 基础延迟: {self.base_delay}s\n")
                f.write("=" * 100 + "\n\n")
        except Exception as e:
            self.logger.error(f"初始化输出文件失败: {e}")
            return False

        print(f"🚀 高速爬取模式启动（分页顺序修复版）")
        print(f"📚 起始章节: {start_url}")
        print(f"💾 保存位置: {output_file}")
        print(f"⚡ 并发数: {self.concurrent_limit} | 基础延迟: {self.base_delay}s")
        print("=" * 80)

        async with await self.create_session() as session:
            current_url = start_url
            chapter_num = 1
            self.chapter_count = 0
            self.total_words = 0
            start_time = time.time()
            consecutive_failures = 0  # 连续失败计数

            while current_url and consecutive_failures < 5:  # 增加失败退出机制
                try:
                    # 异步爬取章节
                    chapter_title, all_content, next_chapter_url = await self.crawl_complete_chapter_async(
                        session, current_url, chapter_num
                    )

                    if not all_content:
                        self.logger.warning(f"章节 {chapter_num} 内容为空，跳过")
                        consecutive_failures += 1
                        current_url = next_chapter_url
                        chapter_num += 1

                        # 如果连续失败，增加延迟
                        if consecutive_failures > 2:
                            await asyncio.sleep(10)
                        continue

                    consecutive_failures = 0  # 重置失败计数

                    # 格式化并保存章节
                    chapter_content = self.format_chapter_content(chapter_title, all_content, chapter_num)

                    if await self.save_chapter_to_file_async(chapter_content, output_file):
                        self.chapter_count += 1
                        chapter_words = sum(len(p) for p in all_content)
                        self.total_words += chapter_words

                        elapsed_time = time.time() - start_time
                        avg_time_per_chapter = elapsed_time / self.chapter_count if self.chapter_count > 0 else 0

                        print(f"✅ 第{chapter_num}章 已保存")
                        print(f"   📖 标题: {chapter_title if chapter_title else '未知'}")
                        print(f"   📊 字数: {chapter_words:,} | 总字数: {self.total_words:,}")
                        print(
                            f"   ⏱️  平均耗时: {avg_time_per_chapter:.1f}s/章 | 服务器负载系数: {self.server_load_factor:.1f}")
                        print()

                    current_url = next_chapter_url
                    chapter_num += 1

                    if not next_chapter_url:
                        print("🎉 已到达最后一章，爬取完成！")
                        break

                except KeyboardInterrupt:
                    print("\n⚠️ 用户中断了爬取过程")
                    break
                except Exception as e:
                    self.logger.error(f"爬取章节 {chapter_num} 时出错: {e}")
                    consecutive_failures += 1
                    current_url = next_chapter_url
                    chapter_num += 1

                    # 错误后增加延迟
                    await asyncio.sleep(5 * consecutive_failures)
                    continue

        # 写入统计信息
        total_time = time.time() - start_time
        try:
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 100 + "\n")
                f.write(f"爬取完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"总章节数: {self.chapter_count}\n")
                f.write(f"总字数: {self.total_words:,}\n")
                f.write(f"总耗时: {total_time:.1f}秒\n")
                f.write(f"平均速度: {self.chapter_count / (total_time / 60):.1f}章/分钟\n")
                f.write(f"失败URL数: {len(self.failed_urls)}\n")
                f.write("=" * 100 + "\n")
        except Exception as e:
            self.logger.error(f"写入统计信息失败: {e}")

        print(f"\n📊 爬取统计:")
        print(f"   📚 总章节数: {self.chapter_count}")
        print(f"   📖 总字数: {self.total_words:,}")
        print(f"   ⏱️  总耗时: {total_time:.1f}秒")
        print(f"   🚀 平均速度: {self.chapter_count / (total_time / 60):.1f}章/分钟")
        print(f"   ❌ 失败请求: {len(self.failed_urls)}")
        print(f"   💾 保存位置: {output_file}")

        return True


# 网络诊断工具类
class NetworkDiagnostic:
    """独立的网络诊断工具"""

    def __init__(self, target_url: str):
        self.target_url = target_url
        self.parsed_url = urlparse(target_url)
        self.host = self.parsed_url.hostname
        self.port = self.parsed_url.port or (443 if self.parsed_url.scheme == 'https' else 80)

    def quick_diagnose(self):
        """快速诊断"""
        print(f"🔧 快速网络诊断: {self.target_url}")
        print("=" * 50)

        # DNS解析测试
        try:
            ip = socket.gethostbyname(self.host)
            print(f"✅ DNS解析成功: {self.host} -> {ip}")
        except socket.gaierror as e:
            print(f"❌ DNS解析失败: {e}")
            print("💡 建议:")
            print("   1. 检查网络连接")
            print("   2. 更换DNS服务器(8.8.8.8)")
            print("   3. 清除DNS缓存: ipconfig /flushdns")
            return False

        # 端口连通性测试
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.host, self.port))
            sock.close()

            if result == 0:
                print(f"✅ 端口 {self.port} 连通")
                return True
            else:
                print(f"❌ 端口 {self.port} 不通")
                print("💡 可能原因:")
                print("   1. 防火墙阻止")
                print("   2. 服务器宕机")
                print("   3. 网络限制")
                return False
        except Exception as e:
            print(f"❌ 连接测试失败: {e}")
            return False


async def main_async():
    """异步主函数"""
    print("🚀 高速小说爬虫工具 - 分页顺序修复版本")
    print("=" * 60)

    try:
        # 获取用户输入
        start_url = input("请输入起始章节URL: ").strip()
        if not start_url:
            start_url = 'https://www.twinfoo.com/post/193117.html'
            print(f"使用默认URL: {start_url}")

        # 先进行网络诊断
        print("\n🔍 进行网络连接测试...")
        diagnostic = NetworkDiagnostic(start_url)
        if not diagnostic.quick_diagnose():
            print("\n❌ 网络连接有问题，建议先解决网络问题再运行爬虫")
            return

        # 输出文件名
        custom_name = input("\n请输入输出文件名（回车使用默认名称）: ").strip()
        if custom_name:
            if not custom_name.endswith('.txt'):
                custom_name += '.txt'
            output_file = custom_name
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"小说_{timestamp}.txt"

        # 并发设置（默认降低）
        concurrent_input = input("请输入并发数（1-5，回车使用推荐值2）: ").strip()
        concurrent_limit = int(concurrent_input) if concurrent_input.isdigit() and 1 <= int(
            concurrent_input) <= 5 else 2

        # 延迟设置（默认增加）
        delay_input = input("请输入基础延迟时间/秒（0.5-5.0，回车使用推荐值1.5）: ").strip()
        try:
            base_delay = float(delay_input) if delay_input else 1.5
            base_delay = max(0.5, min(5.0, base_delay))  # 限制范围
        except ValueError:
            base_delay = 1.5

        print(f"\n⚙️ 配置确认:")
        print(f"   🔗 并发数: {concurrent_limit}")
        print(f"   ⏱️  基础延迟: {base_delay}s")
        print(f"   📁 输出文件: {output_file}")
        print()

        # 创建高速爬虫实例（修复版）
        crawler = FastNovelCrawler(
            concurrent_limit=concurrent_limit,
            base_delay=base_delay
        )

        # 开始异步爬取
        success = await crawler.crawl_novel_from_chapter_async(start_url, output_file)

        if success:
            print(f"\n✅ 小说爬取完成！")
            print(f"📖 文件保存在: {output_file}")
        else:
            print("\n❌ 爬取过程中出现错误，请检查日志文件")

    except KeyboardInterrupt:
        print("\n⚠️ 用户中断了程序")
    except Exception as e:
        print(f"\n❌ 程序执行出错: {e}")


def main():
    """同步主函数入口"""
    asyncio.run(main_async())


# 独立的网络测试工具
def test_network():
    """独立的网络测试功能"""
    print("🔧 网络连接测试工具")
    print("=" * 40)

    url = input("请输入要测试的网站URL: ").strip()
    if not url:
        url = "https://www.twinfoo.com"

    diagnostic = NetworkDiagnostic(url)
    success = diagnostic.quick_diagnose()

    if success:
        print(f"\n✅ 网站 {url} 连接正常")
    else:
        print(f"\n❌ 网站 {url} 连接有问题")
        print("\n🛠️ 常见解决方案:")
        print("1. 检查网络连接是否正常")
        print("2. 更换DNS服务器:")
        print("   - Google DNS: 8.8.8.8, 8.8.4.4")
        print("   - 114 DNS: 114.114.114.114")
        print("3. 清除DNS缓存:")
        print("   - Windows: ipconfig /flushdns")
        print("   - macOS: sudo dscacheutil -flushcache")
        print("4. 临时关闭防火墙测试")
        print("5. 检查代理设置")
        print("6. 尝试使用VPN")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # 运行网络测试
        test_network()
    else:
        # 运行主程序
        main()

"""
分页顺序修复版本说明:

主要修复内容:
1. ✅ 新增 _extract_page_number() 方法: 从URL中智能提取页码
2. ✅ 新增 _sort_pagination_urls() 方法: 对分页URL按页码排序
3. ✅ 新增 _deduplicate_preserve_order() 方法: 去重但保持顺序
4. ✅ 改进 get_pagination_links() 方法: 
   - 扩展分页链接查找策略
   - 过滤导航链接（上一页、下一页）
   - 智能排序分页链接
5. ✅ 修复 crawl_complete_chapter_async() 方法:
   - 改为按顺序爬取分页（不再并发）
   - 保存索引确保内容顺序正确
   - 添加分页爬取进度显示

修复的核心问题:
- 原代码使用 list(set()) 去重，破坏了分页顺序
- 并发爬取分页时没有保证内容插入顺序
- 缺少分页URL的排序逻辑
- 分页链接提取策略单一

现在分页内容会按正确顺序排列！
"""