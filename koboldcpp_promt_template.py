def debug_print(*args, **kwargs):
    print(*args, **kwargs)


class UserDefinedTags:
    def __init__(self) -> None:
        self.ignore_following = '<IgnoreFollowing>'
        self.story_mode = '<StoryMode>'
        self.comment_start = '<Comment>'
        self.comment_end = '</Comment>'
        
        self.reserved_owners = [
            'sys', 'user', 'model'
        ]
        
        self.has_other = False
        
        
    def apply_config(self, config: dict):
        self.sys_start = config['sys_start']
        self.sys_end = config['sys_end']
        self.user_start = config['user_start']
        self.user_end = config['user_end']
        self.model_start = config['model_start']
        self.model_end = config['model_end']
        
        self.has_other = 'other_start' in config and 'other_end' in config
        if self.has_other:
            self.other_start = config['other_start']
            self.other_end = config['other_end']
        
        self.header_postfix = config['header_postfix'] if 'header_postfix' in config else ''
        self.end_prefix = config['end_prefix'] if 'end_prefix' in config else ''


class TemplateHelper:
    def __init__(self) -> None:
        self.continuous_generation = False
        self.no_next_line = False
        self.story_mode = False
        
        self.user_tags = UserDefinedTags()
        
        import json
        with open(r"D:\GGUF.CPP\tkn_configs.json", 'r', encoding='utf-8') as f:
            self.config_file = json.load(f)
            
        self.switch_model('llama')
        
        self.comment_on = False
        self.section_start = False
        self.paragraph_start = False
        
        self.section_owner = ''
        self.allow_strip_section = True
        
        self.user_alias = None
        self.model_alias = None
        self.sys_alias = None
        
        
    def make_block(self, name: str, content: str,
                   with_start=True, with_end=True,
                   new_line=False):
        match name:
            case 'sys':
                start = self.user_tags.sys_start
                end = self.user_tags.sys_end
            case 'user':
                start = self.user_tags.user_start
                end = self.user_tags.user_end
            case 'model':
                start = self.user_tags.model_start
                end = self.user_tags.model_end
            case _:
                start = self.user_tags.other_start +\
                    name + self.user_tags.other_postfix
                end = self.user_tags.other_end
        start = start if with_start else ''
        end = end if with_end else ''
        return start + content + end + ('\n' if new_line else '')
    
    
    def process_paragraph(self, cur_paragraph: str):
        paragraph = cur_paragraph + '\n'
        return paragraph
    
    
    def process_section(self, cur_section: list[str]):
        section = ''
        self.allow_strip_section = True
        debug_print('当前section owner:', self.section_owner)
        debug_print('当前section:', cur_section)
        
        for line in cur_section:
            # 处理注释
            if self.user_tags.comment_end in line:
                self.comment_on = False
                line = line[line.find(self.user_tags.comment_end) + len(self.user_tags.comment_end):]
            if self.comment_on:
                continue
            if self.user_tags.comment_start in line:
                self.comment_on = True
                line = line[:line.find(self.user_tags.comment_start)]
            
            section += self.process_paragraph(line)
            
        if self.allow_strip_section:
            section = section.strip()
                
        # 处理故事模式
        if self.story_mode:
            self.section_owner = 'Narrator'

        if len(self.section_owner) > 0:
            section_name = ''
            if self.section_owner == self.user_alias:
                section_name = 'user'
            elif self.section_owner == self.sys_alias:
                section_name = 'sys'
            elif self.section_owner == self.model_alias:
                section_name = 'model'
            elif self.section_owner in self.user_tags.reserved_owners:
                section_name = self.section_owner
            elif self.user_tags.has_other:
                section_name = self.section_owner
            else:
                raise Exception('未知的section owner！')
            debug_print('当前section name:', section_name)
            debug_print('no_next_line:', self.no_next_line)
            debug_print('continuous_generation:', self.continuous_generation)
            section = self.make_block(section_name, section,
                                      with_end = not self.continuous_generation,
                                      new_line = not self.no_next_line)
            debug_print('当前section:', section)
            
        return section
    
    
    def process_prompt(self, prompt: str):
        sections, current_section = [], []
        lines: list[str] = prompt.split('\n')
        for idx in range(len(lines)):
            new_section = False
            section_owner_new = ''
            line = lines[idx]
            
            if line == len(lines) - 1 and self.story_mode:
                self.no_next_line = True
                self.continuous_generation = True
            
            colon = line.find(':')
            if colon != -1:
                section_owner_new = line[:colon]
                line = line[colon + 1:]
                new_section = True
            
            # 处理忽略
            if self.user_tags.ignore_following in line:
                self.no_next_line = True
                self.continuous_generation = True
                line = line[:line.find(self.user_tags.ignore_following)]
                current_section.append(line)
                sections.append(
                    self.process_section(current_section))
                break
            
            if new_section:
                if self.section_start:
                    sections.append(
                        self.process_section(current_section))
                    current_section = []
                self.section_owner = section_owner_new
                self.section_start = True
                
            current_section.append(line)
            
        if len(current_section) > 0:
            sections.append(
                self.process_section(current_section))
            current_section = []
            
        sections = '\n'.join(sections)
        if self.no_next_line:
            sections = sections.strip()
            
        return sections
                
        
    def switch_model(self, model_name: str, model_version: str|None = None):
        configs = list(filter(lambda x: x['model'] == model_name, self.config_file))
        if model_version is not None:
            config = list(filter(lambda x: x['version'] == model_version, configs))[0]
        else:
            config = configs[0]
        if len(config) == 0:
            raise Exception('未找到对应模型的配置文件！')
        self.user_tags.apply_config(config)
        
        
prompt_template_state = TemplateHelper()


def llama_prompt_template(prompt, memory):
    system = ''
    if memory.startswith('System:'):
        system, memory = memory[7:].split('|')
        system = '<|start_header_id|>system<|end_header_id|>\n' + system + '\n<|eot_id|>\n'
    memory = '<|start_header_id|>memory<|end_header_id|>\n' + memory + '\n<|eot_id|>'
    prompt = system + prompt
    return prompt, memory


def phi3_prompt_template(prompt: str, memory: str):
    if prompt_template_state.user_tags.ignore_following in prompt:
        prompt = prompt[:prompt.rfind(prompt_template_state.user_tags.ignore_following)]
        prompt_template_state.no_next_line = True
        prompt_template_state.continuous_generation = True
    system = ''
    
    if prompt_template_state.user_tags.story_mode in memory:
        memory = ''
        system = '<|system|>system\n以下内容是中篇小说\n<|end|>\n'
        prompt_template_state.story_mode = True
        debug_print('进入故事模式')
    else:
        if memory.startswith('System:'):
            system, memory = memory[7:].split('|')
            system = '<|im_start|>system\n' + system + '\n<|im_end|>\n'
        memory = '<|im_end|>\n<|im_start|>memory\n' + memory.strip() + ''
    
    prompt = prompt_template_state.process_prompt(prompt)
        
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
            chat = line[colon + 1:]
            if prompt_template_state.story_mode:
                if chat_started:
                    chater = ''
                    start_tag = ''
                else:
                    chater = 'Narrator\n'
                    start_tag = '<|im_start|>'
            else:
                chater = line[:colon]
                start_tag = '<|im_end|>\n<|im_start|>' if chat_started else '<|im_start|>'
                chater = chater + '\n' if len(chat.strip()) > 0 else ''
            
            line = start_tag + chater + chat
                
            if len(line.strip()) > 0:
                chat_history.append(line)
            chat_started = True
            latest_chat = idx
            
    if chat_started and len(memory) > 0:
        chat_history.insert(latest_chat, memory)
    
    prompt = '\n'.join(chat_history)
    prompt = system + prompt
    
    if not prompt.endswith('\n'):
        prompt = prompt + '\n'
    if prompt_template_state.no_next_line:
        prompt = prompt.strip()
        
    return prompt, ''


def prompt_template(prompt, memory):
    global prompt_template_state
    prompt_template_state = TemplateHelper()
    print('进入提示词模板生成函数')
    prompt, memory = phi3_prompt_template(prompt, memory)
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