import os
import sys
import time
import requests
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


class CloudflareDDNS:
    def __init__(self):
        # 从环境变量获取配置，现在只需要API Token
        self.api_token = os.getenv("CF_API_TOKEN")
        self.zone_id = os.getenv("CF_ZONE_ID")
        self.record_name = os.getenv("CF_RECORD_NAME")
        self.check_interval = int(
            os.getenv("CHECK_INTERVAL", "300")
        )  # 默认5分钟检查一次

        if not all([self.api_token, self.zone_id, self.record_name]):
            logging.error("环境变量 CF_API_TOKEN, CF_ZONE_ID 或 CF_RECORD_NAME 未设置")
            sys.exit(1)

        # 使用Bearer令牌认证
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        self.api_base = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}"

    def get_current_ip(self):
        """获取当前公网IP"""
        try:
            # 使用Cloudflare的trace接口获取IP，更可靠
            response = requests.get("https://1.1.1.1/cdn-cgi/trace")
            for line in response.text.splitlines():
                if line.startswith("ip="):
                    return line.split("=")[1]
            return None
        except Exception as e:
            logging.error(f"获取公网IP失败: {str(e)}")
            return None

    def verify_token(self):
        """验证API Token是否有效"""
        try:
            response = requests.get(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers=self.headers,
            )
            return response.status_code == 200
        except Exception as e:
            logging.error(f"API Token验证失败: {str(e)}")
            return False

    def get_dns_record(self):
        """获取DNS记录"""
        try:
            response = requests.get(
                f"{self.api_base}/dns_records",
                headers=self.headers,
                params={"name": self.record_name, "type": "A"},
            )
            response.raise_for_status()
            records = response.json()["result"]
            return records[0] if records else None
        except Exception as e:
            logging.error(f"获取DNS记录失败: {str(e)}")
            return None

    def update_dns_record(self, record_id, ip):
        """更新DNS记录"""
        try:
            data = {
                "type": "A",
                "name": self.record_name,
                "content": ip,
                "proxied": True,
            }

            response = requests.put(
                f"{self.api_base}/dns_records/{record_id}",
                headers=self.headers,
                json=data,
            )
            response.raise_for_status()
            return response.json()["success"]
        except Exception as e:
            logging.error(f"更新DNS记录失败: {str(e)}")
            return False

    def run(self):
        """主运行循环"""
        if not all([self.api_token, self.zone_id, self.record_name]):
            logging.error("缺少必要的环境变量配置")
            return

        # 启动时验证Token
        if not self.verify_token():
            logging.error("API Token无效")
            return

        logging.info("DDNS服务启动")
        last_ip = None

        while True:
            try:
                current_ip = self.get_current_ip()
                if not current_ip:
                    logging.error("无法获取当前IP")
                    time.sleep(60)  # 如果获取IP失败，等待较短时间后重试
                    continue

                # 如果IP没有变化，跳过DNS查询
                if current_ip == last_ip:
                    logging.debug(f"IP未变更: {current_ip}")
                    time.sleep(self.check_interval)
                    continue

                dns_record = self.get_dns_record()
                if not dns_record:
                    logging.error("无法获取DNS记录")
                    time.sleep(60)
                    continue

                if dns_record["content"] != current_ip:
                    logging.info(f"IP已变更: {dns_record['content']} -> {current_ip}")
                    if self.update_dns_record(dns_record["id"], current_ip):
                        logging.info("DNS记录更新成功")
                        last_ip = current_ip
                    else:
                        logging.error("DNS记录更新失败")
                else:
                    logging.info("DNS记录已是最新")
                    last_ip = current_ip

            except Exception as e:
                logging.error(f"发生错误: {str(e)}")

            time.sleep(self.check_interval)


if __name__ == "__main__":
    ddns = CloudflareDDNS()
    ddns.run()
