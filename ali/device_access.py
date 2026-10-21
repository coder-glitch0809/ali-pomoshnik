"""Only the server's local browser may request access to this machine's apps."""
from contextvars import ContextVar

local_request = ContextVar('ali_local_request', default=False)
DESKTOP_MODULES = {'pc','system','photoshop','coreldraw','autocad','max3d','coding','ai_apps'}

def is_desktop(skill):
    return skill.func.__module__.rsplit('.',1)[-1] in DESKTOP_MODULES
