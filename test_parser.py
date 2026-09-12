import asyncio
import json

from app.javbus import query_javbus


async def main():
    code = input("请输入要测试的番号，例如 SSIS-001：").strip()

    try:
        result = await query_javbus(code)

        print("\n===== 查询成功 =====")
        print("番号：", result["code"])
        print("标题：", result["title"])
        print("封面：", result["cover"])
        print("Magnet 数量：", len(result["magnets"]))

        for index, magnet in enumerate(result["magnets"], 1):
            print(f"\n--- Magnet {index} ---")
            print("大小：", magnet["size"])
            print("链接：", magnet["link"])

        with open(
            "test_result.json",
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                result,
                f,
                ensure_ascii=False,
                indent=2
            )

        print("\n结果已保存到 test_result.json")

    except Exception as exc:
        print("\n===== 查询失败 =====")
        print(type(exc).__name__, str(exc))


if __name__ == "__main__":
    asyncio.run(main())