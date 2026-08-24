import re
from typing import Optional, Tuple

def extract_github_owner_repo(github_url: Optional[str]) -> Optional[Tuple[str, str]]:
    if not github_url:
        return None
        
    pattern = r"github\.com[/:](?P<owner>[^/]+)/(?P<repo>[^/\s#\?]+)"
    match = re.search(pattern, github_url.strip())
    
    if not match:
        return None
        
    owner = match.group("owner")
    repo = match.group("repo")
    
    if repo.endswith(".git"):
        repo = repo[:-4]
        
    return owner, repo