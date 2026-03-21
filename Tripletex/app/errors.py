class UnsupportedTaskError(Exception):
    def __init__(self, prompt: str, *args: object) -> None:
        super().__init__(f"Unsupported task for prompt: {prompt[:80]}...", *args)


class MissingPrerequisiteError(Exception):
    def __init__(self, issue: str, detail: str) -> None:
        super().__init__(detail)
        self.issue = issue
        self.detail = detail
