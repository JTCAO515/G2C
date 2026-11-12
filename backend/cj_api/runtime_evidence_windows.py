"""Disjoint existing diagnostic windows and canonical runtime capture."""


class EvidenceWindows:
    def __init__(self,runtime,diagnostic):
        if runtime.runtime_scopes & {scope for scope,_ in diagnostic.selected}:
            raise ValueError('overlapping runtime and diagnostic evidence scopes')
        self.windows=(runtime,diagnostic)
        self.intake_enabled=runtime.intake_enabled or diagnostic.intake_enabled

    def captures_model(self,binding):
        return any(window.captures_model(binding) for window in self.windows)

    def record(self,*args):
        for window in self.windows:window.record(*args)

    def record_intake(self,*args):
        for window in self.windows:window.record_intake(*args)

    def record_model(self,*args):
        for window in self.windows:window.record_model(*args)

    def record_model_input(self,*args):
        for window in self.windows:window.record_model_input(*args)
