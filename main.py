import ccxt
import pandas as pd
import time
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from threading import Thread
import ta.trend as trend 
from datetime import datetime, timedelta, timezone

# --- Настройки ---
SYMBOL = 'WALUSDT'  
TIMEFRAME = '1m' 
MA_PERIOD = 20
UPDATE_INTERVAL = 1 

# Цвета для дифференциации бирж (HEX RRGGBB)
EXCHANGE_COLORS = {
    'Binance': 'ffcc00',  # Желтый
    'Bybit': '0099ff',    # Синий
    'Okx': '66cc00'       # Зеленый
}

class CryptoTracker(App):
    
    def build(self):
        self.is_running = False
        self.analysis_event = None
        self.ohlcv_data = pd.DataFrame() 
        self.selected_exchange = None
        
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # 1. Заголовок
        layout.add_widget(Label(text=f"[b]ФЬЮЧЕРС БОТ[/b]\n{SYMBOL} / {TIMEFRAME} - {UPDATE_INTERVAL}c Опрос", 
                                font_size='24sp', size_hint_y=0.15, markup=True))
        
        # 2. Выбор Биржи
        exchange_layout = BoxLayout(size_hint_y=0.1)
        exchange_layout.add_widget(Label(text="Биржа:", size_hint_x=0.3))
        self.exchange_spinner = Spinner(
            text='Binance',
            values=('Binance', 'Bybit', 'Okx'),
            size_hint=(0.7, 1)
        )
        self.exchange_spinner.bind(text=self.update_exchange_color) # Обновление цвета при смене биржи
        exchange_layout.add_widget(self.exchange_spinner)
        layout.add_widget(exchange_layout)
        
        # 3. Обратный отсчет и статус
        self.countdown_label = Label(text="Обратный отсчет: N/A", 
                                     font_size='18sp', size_hint_y=0.08, markup=True)
        layout.add_widget(self.countdown_label)
        
        self.status_label = Label(text="Выберите биржу и нажмите Старт.", 
                                  font_size='16sp', size_hint_y=0.08, markup=True)
        layout.add_widget(self.status_label)
        
        # 4. Область для вывода результатов анализа
        self.result_label = Label(text="--- Результат ТА ---\nТекущая цена: N/A\nSMA_20 (1m): N/A\nСигнал: N/A", 
                                  font_size='18sp',
                                  halign='left', valign='top', markup=True, size_hint_y=0.3) 
        layout.add_widget(self.result_label)

        # 5. Свечные данные (текстовый вывод)
        self.ohlcv_label = Label(text="--- Последние свечи (1m) ---\nОжидание данных...",
                                 font_size='14sp',
                                 halign='left', valign='top', markup=True, size_hint_y=0.3)
        layout.add_widget(self.ohlcv_label)


        # 6. Кнопка СТАРТ/СТОП
        self.control_button = Button(text="СТАРТ АНАЛИЗА", 
                                     size_hint_y=0.15, font_size='22sp')
        self.control_button.bind(on_press=self.toggle_analysis)
        layout.add_widget(self.control_button)
        
        # Инициализация цвета биржи при запуске
        self.update_exchange_color(self.exchange_spinner, self.exchange_spinner.text)
        
        return layout

    def update_exchange_color(self, spinner, text):
        """Обновляет цвет фона в зависимости от выбранной биржи."""
        color = EXCHANGE_COLORS.get(text, 'ffffff')
        self.countdown_label.color = (int(color[0:2], 16)/255, int(color[2:4], 16)/255, int(color[4:6], 16)/255, 1)
        self.status_label.color = self.countdown_label.color
        self.result_label.color = self.countdown_label.color
        self.ohlcv_label.color = self.countdown_label.color


    def get_exchange(self, exchange_name):
        """Получает объект ccxt для фьючерсов."""
        options = {'options': {'defaultType': 'future'}}
        if exchange_name == 'Binance':
            return ccxt.binance(options)
        elif exchange_name == 'Bybit':
            return ccxt.bybit(options)
        elif exchange_name == 'Okx':
            return ccxt.okx(options)
        return None

    def update_status_text(self, text):
        """Простой метод для безопасного обновления статуса в основном потоке."""
        self.status_label.text = text

    def toggle_analysis(self, instance):
        """Запускает или останавливает циклический анализ."""
        if not self.is_running:
            try:
                self.selected_exchange = self.get_exchange(self.exchange_spinner.text)
                if not self.selected_exchange:
                    raise Exception("Неизвестная биржа.")
            except Exception as e:
                self.update_error_ui(f"Ошибка биржи: {e.__class__.__name__}")
                return

            self.is_running = True
            self.control_button.text = "СТОП АНАЛИЗА"
            
            # 1. Запускаем загрузку данных и обратный отсчет
            Thread(target=self.initial_data_load).start()
            self.countdown_event = Clock.schedule_interval(self.update_countdown, 0.2)


        else:
            self.is_running = False
            self.control_button.text = "СТАРТ АНАЛИЗА"
            self.status_label.text = "Анализ остановлен пользователем."
            if self.analysis_event:
                self.analysis_event.cancel()
            if hasattr(self, 'countdown_event') and self.countdown_event:
                 self.countdown_event.cancel()

    def initial_data_load(self):
        """Загружает свечи OHLCV и запускает тикер-опрос."""
        
        Clock.schedule_once(lambda dt: self.update_status_text("Загрузка 1-минутных свечей для ТА..."), 0)
        
        try:
            # 1. Получаем свечи
            ohlcv = self.selected_exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=10)
            
            header = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
            self.ohlcv_data = pd.DataFrame(ohlcv, columns=header)
            
            # 2. Расчет SMA (ИСПРАВЛЕННЫЙ ИМПОРТ)
            self.ohlcv_data['SMA_20'] = trend.sma_indicator(self.ohlcv_data['Close'], window=MA_PERIOD)
            
            # 3. Запуск тикер-опроса
            Clock.schedule_once(lambda dt: self.update_status_text("Данные загружены. Запуск 1-секундного опроса..."), 0)
            self.analysis_event = Clock.schedule_interval(self.fetch_and_update_ticker, UPDATE_INTERVAL)
            
            # 4. Обновление OHLCV-блока
            Clock.schedule_once(lambda dt: self.display_ohlcv_data(), 0)

        except Exception as e:
            error_message = f"Ошибка OHLCV: {e.__class__.__name__}: Проверьте символ {SYMBOL} или API."
            Clock.schedule_once(lambda dt: self.update_error_ui(error_message), 0)

    def update_countdown(self, dt):
        """Обновляет обратный отсчет до закрытия 1m свечи."""
        now = datetime.now(timezone.utc)
        # Получаем время начала текущей минуты
        start_of_minute = now.replace(second=0, microsecond=0)
        # Время закрытия свечи - начало минуты + 60 секунд
        end_of_minute = start_of_minute + timedelta(minutes=1)
        
        time_left = end_of_minute - now
        
        # Обновляем только UI
        seconds_left = time_left.seconds
        
        if seconds_left <= 5 and seconds_left > 0:
            color = '[color=ff0000]' # Красный, если меньше 5 секунд
        else:
            color = '[color=00ffff]' # Голубой

        if seconds_left == 0 and now.microsecond < 200000:
            # Свеча закрылась, нужно обновить OHLCV (запускаем в отдельном потоке)
            Thread(target=self.initial_data_load).start()
            self.countdown_label.text = f"{color}ИДЕТ ОБНОВЛЕНИЕ...[/color]"
        else:
            self.countdown_label.text = f"{color}Обратный отсчет (1m): {seconds_left:02d}c[/color]"

    def display_ohlcv_data(self):
        """Форматирует и выводит последние 5 свечей в Label."""
        
        # Получаем 5 последних свечей (исключая текущую незакрытую)
        recent_candles = self.ohlcv_data.iloc[-6:-1] 
        if recent_candles.empty:
            self.ohlcv_label.text = "--- Последние свечи (1m) ---\nНет данных для отображения."
            return

        output = "--- Последние 5 свечей (1m) ---\n"
        
        # Итерируемся по свечам снизу вверх (от самой старой)
        for index, row in recent_candles.iloc[-5:].iterrows():
            close = row['Close']
            open_price = row['Open']
            
            # Определяем цвет свечи
            color = '00ff00' if close >= open_price else 'ff0000'
            
            # Форматирование времени в UTC
            time_utc = datetime.fromtimestamp(row['Timestamp'] / 1000, tz=timezone.utc).strftime('%H:%M')
            
            output += (
                f"[color={color}]{time_utc} | O:{open_price:,.4f} C:{close:,.4f}[/color]\n"
            )
        
        self.ohlcv_label.text = output


    def fetch_and_update_ticker(self, dt):
        """Получает текущую цену (тикер) и выполняет ТА."""
        if not hasattr(self, '_ticker_thread') or not self._ticker_thread.is_alive():
            self._ticker_thread = Thread(target=self.run_analysis_and_update)
            self._ticker_thread.start()

    def run_analysis_and_update(self):
        """Получает текущую цену (тикер) и сравнивает ее с SMA."""
        try:
            ticker = self.selected_exchange.fetch_ticker(SYMBOL)
            last_price = ticker['last']
            
            # Последняя рассчитанная SMA из 1-минутных данных
            last_sma = self.ohlcv_data['SMA_20'].iloc[-1]
            
            if last_price > last_sma:
                signal_text = "ЛОНГ. [color=00ff00]Цена ВЫШЕ SMA.[/color]"
            elif last_price < last_sma:
                signal_text = "ШОРТ. [color=ff0000]Цена НИЖЕ SMA.[/color]"
            else:
                signal_text = "НЕЙТРАЛЬНО."

            Clock.schedule_once(lambda dt: self.update_ui(last_price, last_sma, signal_text), 0)

        except Exception as e:
            error_message = f"Ошибка TICKER: {e.__class__.__name__}\nПроверьте символ {SYMBOL} на {self.exchange_spinner.text}."
            Clock.schedule_once(lambda dt: self.update_error_ui(error_message), 0)

    def update_ui(self, price, sma, signal):
        """Обновляет Label в основном потоке Kivy."""
        self.result_label.text = (
            f"Биржа: [b]{self.exchange_spinner.text}[/b]\n"
            f"Текущая цена (TICKER): [b]${price:,.4f}[/b]\n"
            f"Скользящая средняя (SMA_{MA_PERIOD}, 1m): ${sma:,.4f}\n"
            f"Сигнал: {signal}"
        )
        self.status_label.text = f"Опрос цены каждые {UPDATE_INTERVAL} сек."

    def update_error_ui(self, message):
        """Обновляет Label при ошибке."""
        self.status_label.text = "ОШИБКА! Анализ остановлен."
        self.result_label.text = f"[color=ff0000]{message}[/color]"
        self.toggle_analysis(self.control_button) 

    def on_stop(self):
        """Останавливает таймер при закрытии приложения."""
        if self.analysis_event:
            self.analysis_event.cancel()
        if hasattr(self, 'countdown_event') and self.countdown_event:
             self.countdown_event.cancel()

if __name__ == '__main__':
    CryptoTracker().run()
