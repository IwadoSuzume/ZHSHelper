import requests

def pushpluser(title: str, content, token: str) -> None:
    requests.get(
        f"http://www.pushplus.plus/send?token={token}&title={title}&content={content}")


def barkpusher(title: str, content, token: str) -> None:
    requests.get(
        f"{token}/{title}/{content}")
