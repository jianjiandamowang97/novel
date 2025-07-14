import asyncio
import aiohttp
import socket
import ssl
import time
from urllib.parse import urlparse
import subprocess
import platform
import dns.resolver
from aiohttp import ClientSession, ClientTimeout, TCPConnector


class NetworkDiagnostic:
    """网络连接诊断工具"""

    def __init__(self, target_url: str = 'https://www.twinfoo.com'):
        self.target_url = target_url
        self.parsed_url = urlparse(target_url)
        self.host = self.parsed_url.hostname
        self.port = self.parsed_url.port or (443 if self.parsed_url.scheme == 'https' else 80)

    def test_basic_connectivity(self):
        """测试基本网络连接"""
        print("🔍 基本网络连接测试")
        print("=" * 50)

        # 1. DNS解析测试
        print(f"1. DNS解析测试: {self.host}")
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = 5
            resolver.lifetime = 5

            # 尝试解析A记录
            answers = resolver.resolve(self.host, 'A')
            ips = [str(answer) for answer in answers]
            print(f"   ✅ DNS解析成功: {ips}")

            # 尝试解析AAAA记录（IPv6）
            try:
                answers_v6 = resolver.resolve(self.host, 'AAAA')
                ips_v6 = [str(answer) for answer in answers_v6]
                print(f"   ✅ IPv6解析成功: {ips_v6}")
            except:
                print(f"   ⚠️ 无IPv6记录")

        except Exception as e:
            print(f"   ❌ DNS解析失败: {e}")
            return False

        # 2. Ping测试
        print(f"\n2. Ping测试: {self.host}")
        try:
            system = platform.system().lower()
            if system == "windows":
                result = subprocess.run(['ping', '-n', '4', self.host],
                                        capture_output=True, text=True, timeout=10)
            else:
                result = subprocess.run(['ping', '-c', '4', self.host],
                                        capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                print(f"   ✅ Ping成功")
                # 提取ping时间
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'time=' in line or 'ms' in line:
                        print(f"   📊 {line.strip()}")
            else:
                print(f"   ❌ Ping失败: {result.stderr}")

        except Exception as e:
            print(f"   ❌ Ping测试失败: {e}")

        # 3. 端口连通性测试
        print(f"\n3. 端口连通性测试: {self.host}:{self.port}")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((self.host, self.port))
            sock.close()

            if result == 0:
                print(f"   ✅ 端口 {self.port} 可访问")
            else:
                print(f"   ❌ 端口 {self.port} 不可访问")

        except Exception as e:
            print(f"   ❌ 端口测试失败: {e}")

        return True

    def test_ssl_certificate(self):
        """测试SSL证书"""
        print(f"\n🔒 SSL证书测试: {self.host}")
        print("=" * 50)

        try:
            context = ssl.create_default_context()

            with socket.create_connection((self.host, self.port), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname=self.host) as ssock:
                    cert = ssock.getpeercert()

                    print(f"   ✅ SSL连接成功")
                    print(f"   📜 证书主题: {cert.get('subject', 'N/A')}")
                    print(f"   🏢 证书颁发者: {cert.get('issuer', 'N/A')}")
                    print(f"   📅 有效期: {cert.get('notBefore', 'N/A')} - {cert.get('notAfter', 'N/A')}")

        except ssl.SSLError as e:
            print(f"   ❌ SSL错误: {e}")
        except Exception as e:
            print(f"   ❌ SSL测试失败: {e}")

    async def test_http_request(self):
        """测试HTTP请求"""
        print(f"\n🌐 HTTP请求测试: {self.target_url}")
        print("=" * 50)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

        timeout = ClientTimeout(total=30, connect=10)
        connector = TCPConnector(
            keepalive_timeout=60,
            enable_cleanup_closed=True,
            ssl=False  # 先尝试不验证SSL
        )

        try:
            async with ClientSession(timeout=timeout, connector=connector, headers=headers) as session:
                start_time = time.time()
                async with session.get(self.target_url) as response:
                    response_time = time.time() - start_time

                    print(f"   ✅ HTTP请求成功")
                    print(f"   📊 状态码: {response.status}")
                    print(f"   ⏱️ 响应时间: {response_time:.2f}秒")
                    print(f"   📄 内容类型: {response.headers.get('Content-Type', 'N/A')}")
                    print(f"   🔍 服务器: {response.headers.get('Server', 'N/A')}")

                    # 读取部分内容
                    content = await response.text()
                    print(f"   📝 内容长度: {len(content)} 字符")

                    if len(content) > 0:
                        print(f"   📖 内容预览: {content[:200]}...")

        except aiohttp.ClientConnectorError as e:
            print(f"   ❌ 连接错误: {e}")
            print(f"   💡 可能原因: 网络不通、DNS解析失败、防火墙阻止")
        except aiohttp.ClientSSLError as e:
            print(f"   ❌ SSL错误: {e}")
            print(f"   💡 可能原因: SSL证书问题、协议不匹配")
        except asyncio.TimeoutError:
            print(f"   ❌ 请求超时")
            print(f"   💡 可能原因: 服务器响应慢、网络延迟高")
        except Exception as e:
            print(f"   ❌ 请求失败: {e}")

    def test_alternative_domains(self):
        """测试备用域名"""
        print(f"\n🔄 备用域名测试")
        print("=" * 50)

        # 常见的备用域名模式
        alternative_domains = [
            self.host.replace('www.', ''),  # 去掉www
            f"www.{self.host}" if not self.host.startswith('www.') else self.host.replace('www.', ''),
            self.host.replace('.com', '.net'),
            self.host.replace('.com', '.org'),
            self.host.replace('.com', '.cn'),
        ]

        for domain in alternative_domains:
            if domain != self.host:
                print(f"   🔍 测试域名: {domain}")
                try:
                    answers = dns.resolver.resolve(domain, 'A')
                    ips = [str(answer) for answer in answers]
                    print(f"      ✅ DNS解析成功: {ips}")
                except:
                    print(f"      ❌ DNS解析失败")

    def suggest_solutions(self):
        """建议解决方案"""
        print(f"\n💡 问题排查建议")
        print("=" * 50)

        solutions = [
            "1. 检查网络连接",
            "   - 确保网络连接正常",
            "   - 尝试访问其他网站",
            "   - 检查代理设置",
            "",
            "2. 检查DNS设置",
            "   - 尝试使用公共DNS (8.8.8.8, 114.114.114.114)",
            "   - 清除DNS缓存: ipconfig /flushdns (Windows)",
            "",
            "3. 检查防火墙设置",
            "   - 临时关闭防火墙测试",
            "   - 检查是否有端口限制",
            "",
            "4. 网站可能的问题",
            "   - 网站服务器可能宕机",
            "   - 域名可能已过期",
            "   - 网站可能更换了域名",
            "",
            "5. 爬虫代码优化",
            "   - 增加重试机制",
            "   - 使用代理服务器",
            "   - 降低并发数",
            "   - 增加请求延迟",
        ]

        for solution in solutions:
            print(solution)

    async def run_full_diagnostic(self):
        """运行完整诊断"""
        print(f"🔧 网络连接诊断工具")
        print(f"🎯 目标网站: {self.target_url}")
        print("=" * 80)

        # 基本连接测试
        self.test_basic_connectivity()

        # SSL证书测试
        if self.parsed_url.scheme == 'https':
            self.test_ssl_certificate()

        # HTTP请求测试
        await self.test_http_request()

        # 备用域名测试
        self.test_alternative_domains()

        # 建议解决方案
        self.suggest_solutions()


async def main():
    """主函数"""
    target_url = input("请输入要诊断的网站URL (回车使用默认): ").strip()
    if not target_url:
        target_url = 'https://www.twinfoo.com'

    diagnostic = NetworkDiagnostic(target_url)
    await diagnostic.run_full_diagnostic()


if __name__ == "__main__":
    # 安装依赖提示
    print("请先安装依赖:")
    print("pip install aiohttp dnspython")
    print()

    asyncio.run(main())