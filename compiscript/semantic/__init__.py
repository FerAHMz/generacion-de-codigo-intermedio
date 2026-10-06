"""Análisis semántico de Compiscript (visitor sobre el árbol de ANTLR)."""

from .analyzer import AnalysisResult, SemanticAnalyzer, analyze, analyze_file

__all__ = ["AnalysisResult", "SemanticAnalyzer", "analyze", "analyze_file"]
