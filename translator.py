"""
Módulo para traducir textos de otros idiomas al español.
Utiliza la biblioteca translate que proporciona una interfaz gratuita para traducciones.
"""

import logging
from translate import Translator

# Configurar logging
logger = logging.getLogger(__name__)

# Diccionario de caché para evitar traducir el mismo texto múltiples veces
translation_cache = {}

def translate_text(text, source_lang='auto', target_lang='es'):
    """
    Traduce un texto desde un idioma de origen a un idioma de destino.
    
    Args:
        text (str): Texto a traducir
        source_lang (str): Idioma de origen (por defecto 'auto' para detección automática)
        target_lang (str): Idioma de destino (por defecto 'es' para español)
        
    Returns:
        str: Texto traducido o el texto original si falla la traducción
    """
    if not text:
        return text
    
    # Limitar el tamaño del texto para evitar problemas
    if len(text) > 5000:
        text = text[:5000]
    
    # Verificar si ya tenemos esta traducción en caché
    cache_key = f"{source_lang}:{target_lang}:{text}"
    if cache_key in translation_cache:
        return translation_cache[cache_key]
    
    try:
        translator = Translator(to_lang=target_lang, from_lang=source_lang)
        translated_text = translator.translate(text)
        
        # Si la traducción contiene [PYFAILURE] o está vacía, retornar el original
        if "[PYFAILURE]" in translated_text or not translated_text:
            logger.warning(f"Falló la traducción: '{text}'")
            return text
        
        # Guardar en caché
        translation_cache[cache_key] = translated_text
        return translated_text
    except Exception as e:
        logger.error(f"Error al traducir: {str(e)}")
        return text  # Devolver el texto original en caso de error