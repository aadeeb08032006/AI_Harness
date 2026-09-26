import os
import re
import string

IGNORE_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv",
               "dist", "build", ".pytest_cache", "outputs"}
MAX_FILE_SIZE_BYTES = 50_000
DEFAULT_TOP_K = 8
SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
                     ".rb", ".rs", ".c", ".cpp", ".h"}


def list_files(repo_path: str) -> list[str]:
    result = []
    for root, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for filename in filenames:
            file_path = os.path.join(root, filename)
            try:
                if os.path.getsize(file_path) > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue
            
            rel_path = os.path.relpath(file_path, repo_path)
            result.append(rel_path)
    return sorted(result)


def _score_file(path: str, task_keywords: set[str]) -> float:
    path_lower = path.lower()
    path_tokens = [t for t in re.split(r'[^a-z0-9]+', path_lower) if t]
    
    score = 0.0
    for keyword in task_keywords:
        if any(keyword in token for token in path_tokens):
            score += 1.0
            
    if os.path.splitext(path)[1] in SOURCE_EXTENSIONS:
        score += 0.5
        
    if "test" in path_lower and any(any(kw in token for token in path_tokens) for kw in task_keywords):
        score += 1.0
        
    return score


def _extract_keywords(task: str) -> set[str]:
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "is", "this", "that", "with"}
    words = task.lower().split()
    keywords = set()
    for word in words:
        cleaned_word = word.translate(str.maketrans('', '', string.punctuation))
        if cleaned_word and cleaned_word not in stopwords:
            keywords.add(cleaned_word)
    return keywords


def build_context(repo_path: str, task: str, top_k: int = DEFAULT_TOP_K) -> dict:
    keywords = _extract_keywords(task)
    all_files = list_files(repo_path)
    
    if not all_files:
        return {"all_files": [], "relevant_files": [], "file_contents": {}}
        
    scored = [(path, _score_file(path, keywords)) for path in all_files]
    scored.sort(key=lambda x: (-x[1], x[0]))
    
    if scored[0][1] == 0:
        scored_fallback = []
        for path in all_files:
            is_source = 1 if os.path.splitext(path)[1] in SOURCE_EXTENSIONS else 0
            depth = path.count(os.sep)
            scored_fallback.append((path, is_source, depth))
        scored_fallback.sort(key=lambda x: (-x[1], x[2], x[0]))
        relevant_files = [path for path, _, _ in scored_fallback[:top_k]]
    else:
        relevant_files = [path for path, score in scored[:top_k]]
        
    file_contents = {}
    for path in relevant_files:
        full_path = os.path.join(repo_path, path)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            file_contents[path] = content
        except UnicodeDecodeError:
            pass
        except OSError:
            pass
            
    return {
        "all_files": all_files,
        "relevant_files": relevant_files,
        "file_contents": file_contents
    }
