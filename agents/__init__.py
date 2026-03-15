def build_root_orchestrator():
	from agents.orchestrator import build_root_orchestrator as _builder

	return _builder()


__all__ = ["build_root_orchestrator"]
