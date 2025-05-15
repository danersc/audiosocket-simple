#!/usr/bin/env python3
"""
Analisador de logs das chamadas.
Este script processa os arquivos de log das chamadas para gerar relatórios
de desempenho e identificar possíveis gargalos.
"""

import json
import os
import sys
import glob
import re
from datetime import datetime
from typing import Dict, List, Tuple, Any
import statistics
import argparse

def parse_log_line(line: str) -> Dict[str, Any]:
    """
    Parse uma linha de log no formato:
    2023-04-23 15:30:45.123 | INFO | EVENT_TYPE | {"key": "value", ...}
    
    Retorna um dicionário com timestamp, level, event_type e data.
    """
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \| (\w+) \| (\w+) \| (.+)'
    match = re.match(pattern, line)
    
    if not match:
        return None
    
    timestamp_str, level, event_type, data_str = match.groups()
    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
    
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        data = {"raw_message": data_str}
    
    return {
        "timestamp": timestamp,
        "level": level,
        "event_type": event_type,
        "data": data
    }

def load_log_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Carrega um arquivo de log e retorna uma lista de eventos parseados.
    """
    events = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            parsed = parse_log_line(line.strip())
            if parsed:
                events.append(parsed)
    
    return events

def calculate_statistics(values: List[float]) -> Dict[str, float]:
    """
    Calcula estatísticas básicas para uma lista de valores.
    """
    if not values:
        return {
            "min": 0,
            "max": 0,
            "avg": 0,
            "median": 0,
            "p90": 0,
            "p95": 0,
            "p99": 0
        }
    
    values = sorted(values)
    n = len(values)
    
    return {
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / n,
        "median": values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2,
        "p90": values[int(n * 0.9)],
        "p95": values[int(n * 0.95)],
        "p99": values[int(n * 0.99)] if n >= 100 else values[-1]
    }

def analyze_transcription_times(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analisa os tempos de transcrição de áudio.
    """
    times = []
    visitor_times = []
    resident_times = []
    
    for i, event in enumerate(events):
        if event["event_type"] == "TRANSCRIPTION_COMPLETE":
            duration = event["data"].get("duration_ms", 0)
            times.append(duration)
            
            if event["data"].get("source") == "visitor":
                visitor_times.append(duration)
            else:
                resident_times.append(duration)
    
    return {
        "all": calculate_statistics(times),
        "visitor": calculate_statistics(visitor_times),
        "resident": calculate_statistics(resident_times)
    }

def analyze_synthesis_times(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analisa os tempos de síntese de áudio.
    """
    times = []
    visitor_times = []
    resident_times = []
    
    for i, event in enumerate(events):
        if event["event_type"] == "SYNTHESIS_COMPLETE":
            duration = event["data"].get("duration_ms", 0)
            times.append(duration)
            
            if event["data"].get("target") == "visitor":
                visitor_times.append(duration)
            else:
                resident_times.append(duration)
    
    return {
        "all": calculate_statistics(times),
        "visitor": calculate_statistics(visitor_times),
        "resident": calculate_statistics(resident_times)
    }

def analyze_ai_processing_times(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analisa os tempos de processamento da IA.
    """
    total_times = []
    intent_extraction_times = {
        "intent_type": [],
        "interlocutor_name": [],
        "apartment_and_resident": []
    }
    fuzzy_validation_times = []
    
    for i, event in enumerate(events):
        if event["event_type"] == "AI_PROCESSING_COMPLETE":
            duration = event["data"].get("duration_ms", 0)
            total_times.append(duration)
        
        elif event["event_type"] == "INTENT_EXTRACTION_COMPLETE":
            duration = event["data"].get("duration_ms", 0)
            stage = event["data"].get("stage")
            if stage in intent_extraction_times:
                intent_extraction_times[stage].append(duration)
        
        elif event["event_type"] == "FUZZY_VALIDATION_COMPLETE":
            duration = event["data"].get("duration_ms", 0)
            fuzzy_validation_times.append(duration)
    
    return {
        "total": calculate_statistics(total_times),
        "intent_extraction": {
            "intent_type": calculate_statistics(intent_extraction_times["intent_type"]),
            "interlocutor_name": calculate_statistics(intent_extraction_times["interlocutor_name"]),
            "apartment_and_resident": calculate_statistics(intent_extraction_times["apartment_and_resident"])
        },
        "fuzzy_validation": calculate_statistics(fuzzy_validation_times)
    }

def analyze_vad_performance(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analisa o desempenho da detecção de voz (VAD).
    """
    speech_durations = []
    silence_durations = []
    
    for i, event in enumerate(events):
        if event["event_type"] == "SPEECH_ENDED":
            duration = event["data"].get("duration_ms", 0)
            speech_durations.append(duration)
        
        elif event["event_type"] == "SILENCE_DETECTED":
            duration = event["data"].get("duration_ms", 0)
            silence_durations.append(duration)
    
    return {
        "speech_durations": calculate_statistics(speech_durations),
        "silence_durations": calculate_statistics(silence_durations)
    }

def analyze_call_durations(events: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Analisa a duração total das chamadas.
    """
    call_start = None
    call_end = None
    
    for event in events:
        if event["event_type"] == "CALL_STARTED":
            call_start = event["timestamp"]
        elif event["event_type"] == "CALL_ENDED":
            call_end = event["timestamp"]
    
    if call_start and call_end:
        return (call_end - call_start).total_seconds() * 1000
    
    return 0

def analyze_errors(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Analisa os erros registrados durante a chamada.
    """
    errors = []
    
    for event in events:
        if event["event_type"] == "ERROR":
            errors.append({
                "timestamp": event["timestamp"],
                "error_type": event["data"].get("error_type", "unknown"),
                "message": event["data"].get("message", ""),
                "details": event["data"].get("details", {})
            })
    
    return errors

def analyze_log_file(filepath: str) -> Dict[str, Any]:
    """
    Analisa um arquivo de log de chamada e gera um relatório.
    """
    call_id = os.path.basename(filepath).replace('.log', '')
    events = load_log_file(filepath)
    
    if not events:
        return {
            "call_id": call_id,
            "error": "Arquivo de log vazio ou formato inválido"
        }
    
    transcription_stats = analyze_transcription_times(events)
    synthesis_stats = analyze_synthesis_times(events)
    ai_processing_stats = analyze_ai_processing_times(events)
    vad_stats = analyze_vad_performance(events)
    call_duration = analyze_call_durations(events)
    errors = analyze_errors(events)
    
    return {
        "call_id": call_id,
        "call_duration_ms": call_duration,
        "transcription_stats": transcription_stats,
        "synthesis_stats": synthesis_stats,
        "ai_processing_stats": ai_processing_stats,
        "vad_stats": vad_stats,
        "errors": errors,
        "event_count": len(events)
    }

def print_stats(title: str, stats: Dict[str, float], indent=0):
    """
    Imprime estatísticas formatadas.
    """
    indentation = " " * indent
    print(f"{indentation}{title}:")
    for key, value in stats.items():
        print(f"{indentation}  {key}: {value:.2f}ms")

def print_report(report: Dict[str, Any]):
    """
    Imprime um relatório formatado.
    """
    print(f"\n==== RELATÓRIO DE CHAMADA: {report['call_id']} ====")
    print(f"Duração total: {report['call_duration_ms']:.2f}ms ({report['call_duration_ms']/1000:.2f}s)")
    print(f"Total de eventos: {report['event_count']}")
    
    print("\n--- TEMPOS DE TRANSCRIÇÃO ---")
    print_stats("Todos", report['transcription_stats']['all'], 2)
    print_stats("Visitante", report['transcription_stats']['visitor'], 2)
    print_stats("Morador", report['transcription_stats']['resident'], 2)
    
    print("\n--- TEMPOS DE SÍNTESE ---")
    print_stats("Todos", report['synthesis_stats']['all'], 2)
    print_stats("Visitante", report['synthesis_stats']['visitor'], 2)
    print_stats("Morador", report['synthesis_stats']['resident'], 2)
    
    print("\n--- TEMPOS DE PROCESSAMENTO IA ---")
    print_stats("Total", report['ai_processing_stats']['total'], 2)
    
    print("\n  Extração de intenção:")
    print_stats("Tipo de intenção", report['ai_processing_stats']['intent_extraction']['intent_type'], 4)
    print_stats("Nome do interlocutor", report['ai_processing_stats']['intent_extraction']['interlocutor_name'], 4)
    print_stats("Apartamento e morador", report['ai_processing_stats']['intent_extraction']['apartment_and_resident'], 4)
    
    print_stats("Validação fuzzy", report['ai_processing_stats']['fuzzy_validation'], 2)
    
    print("\n--- DETECÇÃO DE VOZ ---")
    print_stats("Duração da fala", report['vad_stats']['speech_durations'], 2)
    print_stats("Duração do silêncio", report['vad_stats']['silence_durations'], 2)
    
    if report['errors']:
        print("\n--- ERROS DETECTADOS ---")
        for i, error in enumerate(report['errors']):
            print(f"  {i+1}. {error['error_type']}: {error['message']}")
            if error['details']:
                for k, v in error['details'].items():
                    print(f"     {k}: {v}")

def main():
    parser = argparse.ArgumentParser(description='Analisador de logs de chamadas')
    parser.add_argument('--call_id', help='ID específico da chamada para analisar')
    parser.add_argument('--all', action='store_true', help='Analisar todos os logs')
    parser.add_argument('--summary', action='store_true', help='Mostrar apenas resumo agregado')
    parser.add_argument('--output', help='Arquivo para salvar o relatório em JSON')
    args = parser.parse_args()
    
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
    
    if args.call_id:
        log_file = os.path.join(logs_dir, f"{args.call_id}.log")
        if not os.path.exists(log_file):
            print(f"Arquivo de log não encontrado: {log_file}")
            return
        
        report = analyze_log_file(log_file)
        print_report(report)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
    
    elif args.all or args.summary:
        log_files = glob.glob(os.path.join(logs_dir, "*.log"))
        
        if not log_files:
            print("Nenhum arquivo de log encontrado.")
            return
        
        all_reports = []
        for log_file in log_files:
            report = analyze_log_file(log_file)
            all_reports.append(report)
            
            if args.all and not args.summary:
                print_report(report)
        
        if args.summary:
            # Agregar estatísticas de todos os relatórios
            transcription_times = []
            synthesis_times = []
            ai_processing_times = []
            call_durations = []
            error_count = 0
            
            for report in all_reports:
                # Coletar tempos de transcrição
                for time_list in [report['transcription_stats']['visitor'], report['transcription_stats']['resident']]:
                    for key in ['avg', 'max']:
                        if time_list.get(key):
                            transcription_times.append(time_list[key])
                
                # Coletar tempos de síntese
                for time_list in [report['synthesis_stats']['visitor'], report['synthesis_stats']['resident']]:
                    for key in ['avg', 'max']:
                        if time_list.get(key):
                            synthesis_times.append(time_list[key])
                
                # Coletar tempos de processamento de IA
                if report['ai_processing_stats']['total'].get('avg'):
                    ai_processing_times.append(report['ai_processing_stats']['total']['avg'])
                
                # Coletar duração da chamada
                if report['call_duration_ms']:
                    call_durations.append(report['call_duration_ms'])
                
                # Contar erros
                error_count += len(report['errors'])
            
            print("\n==== RESUMO AGREGADO DE TODAS AS CHAMADAS ====")
            print(f"Total de chamadas analisadas: {len(all_reports)}")
            print(f"Total de erros encontrados: {error_count}")
            
            print("\n--- MÉDIAS GERAIS ---")
            print(f"Duração média das chamadas: {statistics.mean(call_durations)/1000:.2f}s")
            print(f"Tempo médio de transcrição: {statistics.mean(transcription_times):.2f}ms")
            print(f"Tempo médio de síntese: {statistics.mean(synthesis_times):.2f}ms")
            print(f"Tempo médio de processamento de IA: {statistics.mean(ai_processing_times):.2f}ms")
            
            print("\n--- MÁXIMOS GERAIS ---")
            print(f"Duração máxima de chamada: {max(call_durations)/1000:.2f}s")
            print(f"Tempo máximo de transcrição: {max(transcription_times):.2f}ms")
            print(f"Tempo máximo de síntese: {max(synthesis_times):.2f}ms")
            print(f"Tempo máximo de processamento de IA: {max(ai_processing_times):.2f}ms")
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(all_reports, f, indent=2, default=str)
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()