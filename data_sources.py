# data_sources.py - заготовка под подключение реальных датасетов

class DataSource:
    """Базовый класс для всех источников данных"""
    
    @staticmethod
    def get_pollen_data(lat, lon):
        """
        TODO: Подключить реальный датасет пыльцы
        Источники: Copernicus Atmosphere Monitoring Service (CAMS), 
                   местные станции пыльцевания
        Возвращает: концентрацию пыльцы (злаки, береза, амброзия и т.д.)
        """
        # Здесь будет реальный запрос к датасету
        # Пока возвращаем структуру с None - явно показываем, что данные не загружены
        return {
            "birch": None,      # береза
            "grass": None,      # злаки  
            "ragweed": None,    # амброзия
            "alder": None,      # ольха
            "source": "not_connected"
        }
    
    @staticmethod
    def get_air_quality_data(lat, lon):
        """
        TODO: Подключить датасет качества воздуха
        Источники: OpenWeatherMap Air Pollution API, 
                   местные станции экологического мониторинга
        Возвращает: PM2.5, PM10, NO2, O3
        """
        return {
            "pm2_5": None,
            "pm10": None,
            "no2": None,
            "o3": None,
            "source": "not_connected"
        }
    
    @staticmethod
    def get_vegetation_data(lat, lon):
        """
        TODO: Подключить данные о растительности
        Источники: Sentinel-2 (космическая съемка), 
                   городские绿地 карты
        Возвращает: тип растительности, плотность
        """
        return {
            "vegetation_type": None,
            "density": None,
            "source": "not_connected"
        }