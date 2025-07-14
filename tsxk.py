import requests
from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError
from bs4 import BeautifulSoup
import time
import logging
from typing import Optional, List
from urllib.parse import urljoin, urlparse
import os
from datetime import datetime
from pathlib import Path


class WebCrawler:
    """网页爬虫类，用于爬取指定网站的文章内容"""

    def __init__(self, base_url: str = 'https://www.twinfoo.com/wxzw', delay: float = 2.0):
        """
        初始化爬虫

        Args:
            base_url: 基础URL
            delay: 请求间隔时间（秒）
        """
        self.base_url = base_url
        self.delay = delay
        self.session = requests.Session()

        # 设置请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session.headers.update(self.headers)

        # 设置日志
        self._setup_logging()

    def _setup_logging(self) -> None:
        """设置日志配置"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('crawler.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _validate_url(self, url: str) -> bool:
        """验证URL格式"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def get_html_content(self, url: str, timeout: int = 10) -> Optional[str]:
        """
        获取网页HTML内容

        Args:
            url: 目标URL
            timeout: 超时时间

        Returns:
            HTML内容字符串，失败返回None
        """
        if not self._validate_url(url):
            self.logger.error(f"无效的URL: {url}")
            return None

        try:
            self.logger.info(f"正在请求: {url}")
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()

            self.logger.info(f"请求成功，状态码: {response.status_code}, 内容长度: {len(response.content)} 字节")
            time.sleep(self.delay)  # 避免过于频繁的请求
            return response.text

        except Timeout:
            self.logger.error(f"请求超时: {url}")
        except ConnectionError:
            self.logger.error(f"网络连接错误: {url}")
        except HTTPError as e:
            self.logger.error(f"HTTP错误: {e}, URL: {url}")
        except RequestException as e:
            self.logger.error(f"请求异常: {e}, URL: {url}")
        except Exception as e:
            self.logger.error(f"未知异常: {type(e).__name__} - {e}, URL: {url}")

        return None

    def parse_html(self, html_content: str) -> Optional[BeautifulSoup]:
        """
        解析HTML内容

        Args:
            html_content: HTML字符串

        Returns:
            BeautifulSoup对象，失败返回None
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            time.sleep(0.1)  # 短暂延迟
            return soup
        except Exception as e:
            self.logger.error(f"HTML解析失败: {e}")
            return None

    # def extract_article_content(self, url: str) -> List[str]:
    #     """
    #     提取文章内容
    #
    #     Args:
    #         url: 文章URL
    #
    #     Returns:
    #         文章段落列表
    #     """
    #     html_content = self.get_html_content(url)
    #     if not html_content:
    #         return []
    #
    #     soup = self.parse_html(html_content)
    #     if not soup:
    #         return []
    #
    #     try:
    #         # 查找包含文章内容的div
    #         article_div = soup.find('div', class_='blurstxt')
    #         if not article_div:
    #             self.logger.warning(f"未找到文章内容div: {url}")
    #             return []
    #
    #         # 提取所有段落
    #         paragraphs = article_div.find_all('p')
    #         if not paragraphs:
    #             self.logger.warning(f"未找到段落内容: {url}")
    #             return []
    #
    #         # 提取文本内容
    #         content_list = []
    #         content_all = []
    #         for p_tag in paragraphs:
    #             text = p_tag.get_text(strip=True)
    #             if text:  # 只保留非空段落
    #                 content_list.append(text)
    #
    #         self.logger.info(f"成功提取 {len(content_list)} 个段落: {url}")
    #         return content_list
    #
    #         nexthrefa = soup.find('a', rel = 'next')
    #         if not nexthref:
    #             self.logger.warning(f"未找到下一章链接: {url}")
    #         nexta = nexthrefa.get('href')
    #         content_all[0] = conten_list
    #         content_all[1] = nexta
    #         return content_all
    #
    #     except Exception as e:
    #         self.logger.error(f"内容提取失败: {e}, URL: {url}")
    #         return []
    from typing import List, Tuple, Optional

    def extract_article_content(self, url: str) -> Tuple[List[str], Optional[str]]:
        """
        提取文章内容和下一章链接

        Args:
            url: 文章URL

        Returns:
            元组包含:
            - 文章段落列表
            - 下一章链接(如果没有则为None)
        """
        html_content = self.get_html_content(url)
        if not html_content:
            return [], None

        soup = self.parse_html(html_content)
        if not soup:
            return [], None

        try:
            # 查找包含文章内容的div
            article_div = soup.find('div', class_='blurstxt')
            if not article_div:
                self.logger.warning(f"未找到文章内容div: {url}")
                return [], None

            # 提取所有段落
            paragraphs = article_div.find_all('p')
            if not paragraphs:
                self.logger.warning(f"未找到段落内容: {url}")
                return [], None

            # 提取文本内容
            content_list = []
            for p_tag in paragraphs:
                text = p_tag.get_text(strip=True)
                if text:  # 只保留非空段落
                    content_list.append(text)

            # 查找下一章链接
            next_url = None
            next_link = soup.find('a', rel='next')
            if next_link:
                next_url = next_link.get('href')
            else:
                self.logger.warning(f"未找到下一章链接: {url}")

            self.logger.info(f"成功提取 {len(content_list)} 个段落: {url}")
            return content_list, next_url

        except Exception as e:
            self.logger.error(f"内容提取失败: {e}, URL: {url}")
            return [], None
    def save_content_to_file(self, content_list: List[str], output_file: str, is_main_page: bool = False) -> bool:
        """
        保存内容到文件

        Args:
            content_list: 内容列表
            output_file: 输出文件路径
            is_main_page: 是否为主页面

        Returns:
            是否保存成功
        """
        try:
            # 确保输出目录存在
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'a', encoding='utf-8') as f:
                for index, text in enumerate(content_list):
                    # 如果是主页面的第一个段落（标题），添加换行置顶
                    if is_main_page and index == 0:
                        f.write(f"{text}\n\n")
                    else:
                        f.write(f"{text}\n")
                f.write('\n' * 5)
            self.logger.info(f"内容已保存到: {output_file}")
            return True

        except Exception as e:
            self.logger.error(f"文件保存失败: {e}")
            return False

    def get_pagination_links(self, url: str) -> List[str]:
        """
        获取分页链接

        Args:
            url: 当前页面URL

        Returns:
            分页链接列表
        """
        html_content = self.get_html_content(url)
        if not html_content:
            return []

        soup = self.parse_html(html_content)
        if not soup:
            return []

        try:
            # 查找分页链接
            page_links = soup.find_all('a', class_='post-page-numbers')
            pagination_urls = []

            for link in page_links:
                href = link.get('href')
                if href and self._validate_url(href):
                    pagination_urls.append(href)

            self.logger.info(f"找到 {len(pagination_urls)} 个分页链接")
            return pagination_urls

        except Exception as e:
            self.logger.error(f"分页链接提取失败: {e}")
            return []

    # def get_latest_article_url(self) -> Optional[str]:
    #     """
    #     获取未读文章URL，以及爬取后续所有未读文章
    #
    #     Returns:
    #         最新文章URL，失败返回None
    #     """
    #     html_content = self.get_html_content(self.base_url)
    #     if not html_content:
    #         return None
    #
    #     soup = self.parse_html(html_content)
    #     if not soup:
    #         return None
    #
    #     try:
    #         # 查找最新文章链接
    #         article_item = soup.find('div', class_='col-md-4 col-sm-12 att-one-item')
    #         if not article_item:
    #             self.logger.error("未找到文章项目")
    #             return None
    #
    #         article_link = article_item.find('a')
    #         if not article_link:
    #             self.logger.error("未找到文章链接")
    #             return None
    #
    #         latest_url = article_link.get('href')
    #         if not latest_url or not self._validate_url(latest_url):
    #             self.logger.error("获取到的文章URL无效")
    #             return None
    #
    #         self.logger.info(f"找到最新文章: {latest_url}")
    #         return latest_url
    #
    #     except Exception as e:
    #         self.logger.error(f"获取最新文章URL失败: {e}")
    #         return None

    def crawl_all_pages(self, output_file: str = None, url: str = None) -> bool:
        """
        爬取所有页面内容

        Args:
            output_file: 输出文件路径

        Returns:
            是否成功完成爬取
        """
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"爬取结果_{timestamp}.txt"
        # 清空输出文件
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"爬取开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        except Exception as e:
            self.logger.error(f"初始化输出文件失败: {e}")
            return False

        # 获取最新文章URL
        latest_article_url = url
        if not latest_article_url:
            self.logger.error("无法获取最新文章URL")
            return False

        while True:
        # 爬取主页面内容
            self.logger.info("开始爬取主页面内容")
            main_content,nexturl = self.extract_article_content(url)
            self.logger.info(f"下一章链接: {nexturl}")
            if main_content:
                self.save_content_to_file(main_content, output_file, is_main_page=True)

            # 获取分页链接并爬取
            pagination_links = self.get_pagination_links(url)

            for i, page_url in enumerate(pagination_links, 1):
                self.logger.info(f"正在爬取第 {i} 个分页: {page_url}")
                page_content,nnexturl = self.extract_article_content(page_url)
                if page_content:
                    self.save_content_to_file(page_content, output_file, is_main_page=False)
                    # 添加进度提示
                if i % 5 == 0:
                    self.logger.info(f"已完成 {i}/{len(pagination_links)} 个分页")
            print('\n' * 5)
            if  nexturl:
                url = nexturl
            else:
                self.logger.info(f"所有章节均爬取")
                break
        self.logger.info(f"爬取完成！结果已保存到: {output_file}")
        return True


def main():
    """主函数"""
    try:
        # 创建爬虫实例
        crawler = WebCrawler(delay=2.0)  # 设置2秒延迟

        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"爬取结果_{timestamp}.txt"
        url = 'https://www.twinfoo.com/post/193117.html'
        # 开始爬取
        success = crawler.crawl_all_pages(output_file,url)

        if success:
            print(f"✅ 爬取成功完成！结果保存在: {output_file}")
        else:
            print("❌ 爬取过程中出现错误，请检查日志文件 crawler.log")

    except KeyboardInterrupt:
        print("\n⚠️ 用户中断了爬取过程")
    except Exception as e:
        print(f"❌ 程序执行出错: {e}")


if __name__ == "__main__":
    main()