import flet as ft
import requests
import sqlite3
from datetime import datetime
from typing import Dict

# SQLite DBのセットアップ
def setup_db():
    conn = sqlite3.connect('weather_forecasts.db')
    cursor = conn.cursor()

    # weather_forecasts テーブル (天気予報のデータ)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS weather_forecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        region_code TEXT,
        date TEXT,
        weather_code TEXT,
        min_temp INTEGER,
        max_temp INTEGER,
        UNIQUE(region_code, date)
    );
    ''')

    # regions テーブル (地域情報)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS regions (
        region_code TEXT PRIMARY KEY,
        region_name TEXT
    );
    ''')

    conn.commit()
    conn.close()

# エリア情報をDBに保存
def save_area_data():
    conn = sqlite3.connect('weather_forecasts.db')
    cursor = conn.cursor()
    
    # すべての地域データをDBに保存
    for code, area in area_cache.items():
        cursor.execute('''
        INSERT OR REPLACE INTO regions (region_code, region_name)
        VALUES (?, ?)
        ''', (code, area["name"]))
    
    conn.commit()
    conn.close()

# データをデータベースに格納する関数
def save_weather_data(region_code: str, forecast_data: Dict):
    conn = sqlite3.connect('weather_forecasts.db')
    cursor = conn.cursor()
    
    weekly_data = forecast_data[1]  # 週間予報データ
    weather_forecasts = weekly_data["timeSeries"][0]
    temp_forecasts = weekly_data["timeSeries"][1]

    for i in range(len(weather_forecasts["timeDefines"])):
        date = weather_forecasts["timeDefines"][i]
        weather_code = weather_forecasts["areas"][0]["weatherCodes"][i]
        try:
            min_temp = temp_forecasts["areas"][0]["tempsMin"][i]
            max_temp = temp_forecasts["areas"][0]["tempsMax"][i]
        except (IndexError, KeyError):
            min_temp = max_temp = None
        
        cursor.execute('''
        INSERT OR IGNORE INTO weather_forecasts 
        (region_code, date, weather_code, min_temp, max_temp)
        VALUES (?, ?, ?, ?, ?)
        ''', (region_code, date, weather_code, min_temp, max_temp))
    
    conn.commit()
    conn.close()

# 過去の天気予報を取得する関数
def fetch_past_weather_data(region_code: str, date: str):
    conn = sqlite3.connect('weather_forecasts.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT date, weather_code, min_temp, max_temp FROM weather_forecasts 
    WHERE region_code = ? AND date = ?
    ''', (region_code, date))
    result = cursor.fetchall()
    conn.close()
    return result

# 地域情報キャッシュを管理する辞書
area_cache: Dict[str, Dict] = {}

# メインページの設定と表示
def main(page: ft.Page):
    page.title = "天気予報アプリ"
    page.theme_mode = "light"  # 初期テーマモード
    progress_bar = ft.ProgressBar(visible=False)

    # エラーメッセージを表示する関数
    def show_error_message(message: str):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message),
            action="閉じる",
            bgcolor=ft.colors.ERROR,
        )
        page.snack_bar.open = True
        page.update()

    # 地域リストの表示
    region_list_view = ft.ListView(
        expand=True,
        spacing=10,
        padding=10,
    )

    # 天気予報表示エリア
    forecast_display = ft.Column(
        expand=True,
        spacing=10,
        alignment=ft.MainAxisAlignment.START,
    )

    # 検索ボックスの動作
    def search_region(e):
        query = search_box.value.lower()
        filtered_regions = {
            code: area
            for code, area in area_cache.items()
            if query in area["name"].lower()
        }
        update_region_menu(filtered_regions)

    # データを取得するための関数
    def fetch_weather_data(url: str) -> Dict:
        try:
            response = requests.get(url)
            response.raise_for_status()  # HTTPエラーを発生させる
            return response.json()
        except requests.RequestException as e:
            show_error_message(f"データ取得エラー: {str(e)}")
            return {}

    # 地域リストの読み込み
    def load_region_data():
        try:
            progress_bar.visible = True
            page.update()
            data = fetch_weather_data("http://www.jma.go.jp/bosai/common/const/area.json")
            if "offices" in data:
                area_cache.update(data["offices"])
                update_region_menu(area_cache)
                save_area_data()  # 地域情報をDBに保存
            else:
                show_error_message("地域データの形式が予期したものと異なります")
        except Exception as e:
            show_error_message(f"地域データの読み込みに失敗しました: {str(e)}")
        finally:
            progress_bar.visible = False
            page.update()

    # 地域メニューを更新する関数
    def update_region_menu(regions):
        region_list_view.controls.clear()
        for code, area in regions.items():
            region_list_view.controls.append(
                ft.ListTile(
                    leading=ft.Icon(ft.icons.LOCATION_ON),
                    title=ft.Text(area["name"]),
                    subtitle=ft.Text(f"地域コード: {code}"),
                    on_click=lambda e, code=code: load_weather_forecast(code),
                )
            )
        page.update()

    # 予報データの読み込み
    def load_weather_forecast(region_code: str):
        try:
            progress_bar.visible = True
            page.update()

            # 週間予報取得
            forecast_url = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{region_code}.json"
            forecast_data = fetch_weather_data(forecast_url)
            if forecast_data:
                save_weather_data(region_code, forecast_data)  # DBに保存
                display_weather_forecast(forecast_data)
            else:
                show_error_message("天気予報データが見つかりません。")
        except Exception as e:
            show_error_message(f"天気予報の取得に失敗しました: {str(e)}")
        finally:
            progress_bar.visible = False
            page.update()

    # 天気予報を表示する関数
    def display_weather_forecast(data: Dict):
        forecast_display.controls.clear()
        try:
            weekly_data = data[1]  # 週間予報データ
            weather_forecasts = weekly_data["timeSeries"][0]
            temp_forecasts = weekly_data["timeSeries"][1]

            # グリッドビューを作成
            grid_view = ft.GridView(
                expand=True,
                runs_count=4,
                max_extent=200,
                child_aspect_ratio=0.8,
                spacing=10,
                run_spacing=10,
                padding=20,
            )

            # 週間予報を表示
            for i in range(len(weather_forecasts["timeDefines"])):
                date = weather_forecasts["timeDefines"][i]
                weather_code = weather_forecasts["areas"][0]["weatherCodes"][i]
                try:
                    min_temp = temp_forecasts["areas"][0]["tempsMin"][i]
                    max_temp = temp_forecasts["areas"][0]["tempsMax"][i]
                except (IndexError, KeyError):
                    min_temp = max_temp = "--"
                
                # 予報を表示するカードを作成
                forecast_card = ft.Card(
                    content=ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Text(format_date(date), size=16, weight="bold"),
                                ft.Text(get_weather_icon(weather_code), size=25),
                                ft.Text(
                                    f"最低 {min_temp if min_temp != '--' else '不明'}°C",
                                    size=16,
                                    color=ft.colors.BLUE,
                                    weight="bold",
                                ),
                                ft.Text(
                                    f"最高 {max_temp if max_temp != '--' else '不明'}°C",
                                    size=16,
                                    color=ft.colors.RED,
                                    weight="bold",
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                            spacing=10,
                        ),
                        padding=20,
                    )
                )
                grid_view.controls.append(forecast_card)
            forecast_display.controls.append(grid_view)
        except (KeyError, IndexError) as e:
            show_error_message("週間予報データの取得に失敗しました。")
        page.update()

    # 日付をフォーマットする
    def format_date(date_str: str) -> str:
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        weekday = weekdays[date.weekday()]
        return f"{date.month}/{date.day}\n({weekday})"

    # 過去の天気予報を表示する関数
    def show_past_weather(region_code: str):
        selected_date = date_picker.value
        past_weather_data = fetch_past_weather_data(region_code, selected_date)
        
        past_forecast_display.controls.clear()
        if past_weather_data:
            for record in past_weather_data:
                date, weather_code, min_temp, max_temp = record
                past_forecast_display.controls.append(
                    ft.Text(f"{format_date(date)}: {get_weather_icon(weather_code)} - 最低 {min_temp}°C, 最高 {max_temp}°C")
                )
        else:
            past_forecast_display.controls.append(ft.Text("過去の天気情報が見つかりません"))
        
        page.update()

    # 天気コードに対応するアイコンを取得
    def get_weather_icon(code: str) -> str:
        icons = {
            "100": "晴れ ☀️",
            "101": "晴れ時々曇り 🌤️",
            "102": "晴れ時々雨 🌦️",
            "200": "曇り ☁️",
            "201": "曇り時々晴れ 🌥️",
            "202": "曇り時々雨 ☁️🌧️",
            "218": "曇り時々雪 ☁️❄️",
            "270": "雪時々曇り ❄️☁️",
            "300": "雨 🌧️",
            "400": "雪 ❄️",
            "500": "雷雨 ⛈️",
            "413": "雪のち雨 ❄️→🌧️",
            "206": "雨時々曇り 🌧️☁️",
            "111": "雨時々晴れ 🌧️☀️",
            "112": "雨時々雪 🌧️❄️",
            "211": "雪時々晴れ ❄️☀️",
            "212": "雪時々曇り ❄️☁️",
            "313": "雪のち雨 ❄️→🌧️",
            "314": "雨のち雪 🌧️→❄️",
            "203": "曇り時々雪 ☁️❄️",
            "302": "雪 ❄️",
            "114": "雪時々晴れ ❄️☀️",
            "402": "大雪 ❄️❄️❄️",
            "204": "雪時々雨 ❄️🌧️",
            "207": "雷雨時々雪 ⛈️❄️",
            "205": "雨時々雪 🌧️❄️",
            "209": "雪時々雷雨 ❄️⛈️",
            "302": "雪 ❄️",
            "103": "晴れ時々曇り 🌤️",
        }
        return icons.get(code, "天気情報なし")

    # ページのデザインとレイアウト設定
    search_box = ft.TextField(
        hint_text="地域名で検索",
        on_change=search_region,
    )

    # 日付選択
    date_picker = ft.DatePicker(on_change=lambda e: show_past_weather(e.control.value))

    # 過去の天気予報表示エリア
    past_forecast_display = ft.Column(
        spacing=10,
        alignment=ft.MainAxisAlignment.START,
    )

    page.add(
        ft.Row(
            [
                ft.Container(
                    width=300,
                    content=ft.Column(
                        controls=[
                            search_box,
                            region_list_view,
                            date_picker,
                        ]
                    ),
                    bgcolor=ft.colors.SURFACE_VARIANT,
                ),
                ft.Container(
                    expand=True,
                    content=forecast_display,
                ),
            ],
            expand=True,
        ),
        progress_bar,
        past_forecast_display,
    )

    # 初期データの読み込み
    load_region_data()


# Fletアプリケーションの実行
ft.app(target=main)
