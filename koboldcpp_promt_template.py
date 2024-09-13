class UserDefinedTags:
    def __init__(self) -> None:
        self.ignore_following = '<IgnoreFollowing>'
        self.story_mode = '<StoryMode>'


class PromptTemplateVars:
    def __init__(self) -> None:
        self.continuous_generation = False
        self.no_next_line = False
        self.story_mode = False
        
        self.user_tags = UserDefinedTags()
        

prompt_template_state = PromptTemplateVars()


def llama_prompt_template(prompt, memory):
    system = ''
    if memory.startswith('System:'):
        system, memory = memory[7:].split('|')
        system = '<|start_header_id|>system<|end_header_id|>\n' + system + '\n<|eot_id|>\n'
    memory = '<|start_header_id|>memory<|end_header_id|>\n' + memory + '\n<|eot_id|>'
    prompt = system + prompt
    return prompt, memory


def qwen_prompt_template(prompt: str, memory: str):
    if prompt_template_state.user_tags.ignore_following in prompt:
        prompt = prompt[:prompt.rfind(prompt_template_state.user_tags.ignore_following)]
        prompt_template_state.no_next_line = True
        prompt_template_state.continuous_generation = True
    system = ''
    
    if prompt_template_state.user_tags.story_mode in memory:
        memory = ''
        system = '<|im_start|>system\n以下内容是中篇小说\n<|im_end|>\n'
        prompt_template_state.story_mode = True
    else:
        if memory.startswith('System:'):
            system, memory = memory[7:].split('|')
            system = '<|im_start|>system\n' + system + '\n<|im_end|>\n'
        memory = '<|im_end|>\n<|im_start|>memory\n' + memory.strip() + ''
        
    chat_history = []
    lines: list[str] = prompt.split('\n')
    chat_started = False
    latest_chat = 0
    for idx in range(len(lines)):
        line = lines[idx]
        colon = line.find(':')
        if colon == -1:
            chat_history.append(line)
        else:
            chater = '' if prompt_template_state.story_mode else line[:colon]
            chat = line[colon + 1:]
            start_tag = '<|im_end|>\n<|im_start|>' if chat_started else '<|im_start|>'
            if len(chat.strip()) > 0:
                line = f'{start_tag}{chater}\n{chat}'
            else:
                line = f'{start_tag}{chater}'
            if len(line.strip()) > 0:
                chat_history.append(line)
            chat_started = True
            latest_chat = idx
    if chat_started:
        chat_history.insert(latest_chat, memory)
    # chat_history[-1] = chat_history[-1][:-2]
    prompt = '\n'.join(chat_history)
    prompt = system + prompt
    if not prompt.endswith('\n'):
        prompt = prompt + '\n'
    if prompt_template_state.no_next_line:
        prompt = prompt.strip()
    return prompt, ''


def prompt_template(prompt, memory):
    global prompt_template_state
    prompt_template_state = PromptTemplateVars()
    print('进入提示词模板生成函数')
    prompt, memory = qwen_prompt_template(prompt, memory)
    print('生成的提示词完毕\n')
    return prompt, memory


def out_post_process(outstr: str):
    print('\n\n======进入输出后处理函数======')
    print('------输出前------')
    print(outstr)
    print('------输出后------')
    outstr = '\r' + outstr
    print(outstr)
    print('======输出后处理完毕======\n\n')
    return outstr