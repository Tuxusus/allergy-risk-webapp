# risk_calculator.py - логика расчёта риска на основе данных

class RiskCalculator:
    """Калькулятор аллергического риска"""
    
    # Весовые коэффициенты для разных факторов (можно будет настраивать)
    WEIGHTS = {
        "pollen_concentration": 0.40,    # 40% - концентрация пыльцы
        "weather_impact": 0.30,          # 30% - погодные условия
        "air_quality": 0.20,             # 20% - качество воздуха
        "vegetation": 0.10               # 10% - растительность рядом
    }
    
    @staticmethod
    def calculate(pollen_data, weather_data, air_quality_data, vegetation_data):
        """
        Расчёт финального риска на основе ВСЕХ источников данных
        Когда данные появятся - начнут работать автоматически
        """
        scores = {}
        
        # 1. Риск от пыльцы (когда данные появятся)
        if pollen_data and pollen_data.get("birch") is not None:
            scores["pollen"] = RiskCalculator._pollen_risk(pollen_data)
        else:
            scores["pollen"] = None  # Нет данных - не учитываем
            
        # 2. Погодный риск (уже работает!)
        if weather_data:
            scores["weather"] = RiskCalculator._weather_risk(weather_data)
        else:
            scores["weather"] = None
            
        # 3. Риск от качества воздуха (когда данные появятся)
        if air_quality_data and air_quality_data.get("pm2_5") is not None:
            scores["air"] = RiskCalculator._air_quality_risk(air_quality_data)
        else:
            scores["air"] = None
            
        # 4. Риск от растительности (когда данные появятся)
        if vegetation_data and vegetation_data.get("vegetation_type"):
            scores["vegetation"] = RiskCalculator._vegetation_risk(vegetation_data)
        else:
            scores["vegetation"] = None
        
        # Финальный расчёт (только по доступным факторам)
        return RiskCalculator._final_risk(scores)
    
    @staticmethod
    def _pollen_risk(pollen_data):
        """Расчёт риска по данным о пыльце"""
        # TODO: когда появятся данные - реализовать логику
        # Пока возвращаем 0 (нет данных = нет вклада в риск)
        return 0
    
    @staticmethod
    def _weather_risk(weather_data):
        """Погодный риск (уже работает!)"""
        risk = 0
        wind = weather_data.get("wind_speed", 0)
        humidity = weather_data.get("humidity", 50)
        temp = weather_data.get("temperature", 10)
        
        if wind and wind > 6:
            risk += 30
        if humidity and humidity < 45:
            risk += 30
        if temp and temp > 15:
            risk += 20
        return risk
    
    @staticmethod
    def _air_quality_risk(air_data):
        """Расчёт риска по качеству воздуха"""
        # TODO: когда появятся данные - реализовать
        # PM2.5 > 35 = высокий риск
        # NO2 > 40 = средний риск
        return 0
    
    @staticmethod
    def _vegetation_risk(veg_data):
        """Расчёт риска по растительности"""
        # TODO: когда появятся данные - реализовать
        # Берёзовые рощи = высокий риск весной
        return 0
    
    @staticmethod
    def _final_risk(scores):
        """Финальный расчёт с учётом весов"""
        total_weight = 0
        weighted_sum = 0
        
        for factor, score in scores.items():
            weight = RiskCalculator.WEIGHTS.get(factor, 0)
            if score is not None:
                weighted_sum += score * weight
                total_weight += weight
        
        if total_weight > 0:
            final_score = weighted_sum / total_weight
        else:
            final_score = 0
            
        return final_score