"""Small allowlisted completion metadata; never retain hidden reasoning or bodies."""
from urllib.parse import urlsplit


def response_summary(response):
    choices=getattr(response,'choices',None) or []
    choice=choices[0] if choices else None
    message=getattr(choice,'message',None)
    reason=getattr(choice,'finish_reason',None)
    content=getattr(message,'content',None)
    usage=getattr(response,'usage',None)
    safe_usage={}
    for key in ('prompt_tokens','completion_tokens','total_tokens'):
        value=getattr(usage,key,None)
        if type(value) is int and 0<=value<2**63:safe_usage[key]=value
    return {'finish_reason':reason if reason in ('stop','length','content_filter','tool_calls','function_call') else 'unknown',
        'usage':safe_usage,'http_status':200,'content_empty':not isinstance(content,str) or not content.strip(),
        'has_other_output':bool(getattr(message,'reasoning_content',None) or getattr(message,'tool_calls',None) or getattr(message,'refusal',None))}


def test_options(config):
    # DeepSeek's official Chat Completions protocol. No vendor fields on proxies.
    return {'extra_body':{'thinking':{'type':'disabled'}}} if urlsplit(config.base_url).hostname=='api.deepseek.com' else {}
