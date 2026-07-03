import json
import pandas as pd

'''def read_players(file_path="scripts/ai_literacy/players.json"):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f" Lỗi: Không tìm thấy file '{file_path}'...")
        return None
    except json.JSONDecodeError as e:
        print(f" Lỗi: File '{file_path}' không đúng định dạng JSON.")
        return None
    df = pd.DataFrame(data)
    return df'''

'''if __name__ == "__main__":
    df = read_players("scripts/ai_literacy/players.json")
    if df is not None:
        print(" Đọc dữ liệu thành công!\n")
        print(df)'''

with open("scripts/ai_literacy/players.json", "r", encoding="utf-8") as file:
    data = json.load(file)

dataframe = pd.DataFrame(data)

print(dataframe)

dataframe.to_csv(
    "scripts/ai_literacy/players.csv",
    index=False,
    encoding="utf-8-sig",
)