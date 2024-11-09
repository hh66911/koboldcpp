import re


def debug_print(*args, **kwargs):
    return
    print(*args, **kwargs)
    print('-' * 100)


class UserDefinedTags:
    def __init__(self) -> None:
        self.ignore_following = '<IgnoreFollowing>'
        self.story_mode = '<StoryMode>'
        self.comment_start = '<Comment>'
        self.comment_end = '</Comment>'
        self.memory_splitter = '-|-|-'

        self.alias_tag = re.compile(r'<Alias:([\w\s]+)-([\w\s]+)>')
        self.pseudo_tag = re.compile(r'<Pseudo:([\w\s,]+)-([\w\s]+)>')

        self.reserved_owners = [
            'sys', 'user', 'model'
        ]

        self.has_other = False

    def apply_config(self, config: dict):
        self.header_postfix = config['header_postfix'] if 'header_postfix' in config else ''
        self.end_prefix = config['end_prefix'] if 'end_prefix' in config else ''

        self.beginning = config['beginning'] if 'beginning' in config else ''

        post_fix_disable = [] if 'disable_postfix' not in config else config['disable_postfix']
        self.sys_start = config['sys_start'] + (self.header_postfix if 'sys' not in post_fix_disable else '')
        self.sys_end = self.end_prefix + config['sys_end']
        self.user_start = config['user_start'] + (self.header_postfix if 'user' not in post_fix_disable else '')
        self.user_end = self.end_prefix + config['user_end']
        self.model_start = config['model_start'] + (self.header_postfix if 'model' not in post_fix_disable else '')
        self.model_end = self.end_prefix + config['model_end']

        self.has_other = 'other_start' in config and 'other_end' in config
        if self.has_other:
            self.other_start = config['other_start']
            self.other_postfix = self.header_postfix if 'other' not in post_fix_disable else ''
            self.other_end = config['other_end']
        else:
            self.other_start = ''
            self.other_postfix = ':\n'
            self.other_end = ''

        debug_print('用户标签配置：', self.__dict__)


class TemplateHelper:
    def __init__(self) -> None:
        self.continuous_generation = False
        self.no_next_line = False
        self.story_mode = False

        self.user_tags = UserDefinedTags()

        import json
        with open(r"D:/GGUF.CPP/koboldcpp/tkn_configs.json", 'r', encoding='utf-8') as f:
            self.config_file = json.load(f)

        self.switch_model('llama')

        self.comment_on = False
        self.section_start = False
        self.paragraph_start = False

        self.section_owner = ''
        self.section_idx = 0
        self.allow_strip_section = True

        self.user_alias = None
        self.model_alias = None
        self.sys_alias = None
        
        self.pseudo_tags = dict()

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

        if not with_start:
            start = ''
        if not with_end:
            end = ''

        return start + content + end + ('\n' if new_line else '')

    def process_paragraph(self, cur_paragraph: str):
        alias_tag = self.user_tags.alias_tag
        alias_values = alias_tag.findall(cur_paragraph)
        cleaned_text = alias_tag.sub(lambda _: "", cur_paragraph)
        for alias in alias_values:
            debug_print('别名:', alias)
            if alias[0] == 'user':
                self.user_alias = alias[1]
            elif alias[0] == 'sys':
                self.sys_alias = alias[1]
            elif alias[0] == 'model':
                self.model_alias = alias[1]
        paragraph = cleaned_text
        
        pseudo_tag = self.user_tags.pseudo_tag
        pseudo_values = pseudo_tag.findall(paragraph)
        cleaned_text = pseudo_tag.sub(lambda _: "", paragraph)
        for pseudo in pseudo_values:
            debug_print('伪装:', pseudo)
            pseudo_chars: list[str] = pseudo[0].split(',')
            for c in pseudo_chars:
                self.pseudo_tags[c.strip()] = pseudo[1]
        paragraph = cleaned_text
            
        return paragraph + '\n'

    def process_section(self, cur_section: list[str]):
        section = ''
        self.allow_strip_section = True
        debug_print('原始section owner:', self.section_owner)
        debug_print('当前section:', cur_section)

        for line in cur_section:
            # 处理注释
            if self.user_tags.comment_end in line:
                self.comment_on = False
                line = line[line.find(
                    self.user_tags.comment_end) + len(self.user_tags.comment_end):]
            if self.comment_on:
                continue
            if self.user_tags.comment_start in line:
                self.comment_on = True
                line = line[:line.find(self.user_tags.comment_start)]

            section += self.process_paragraph(line)

        if self.allow_strip_section:
            section = section.strip()

        with_start, with_end = True, True
        new_line = True

        # 处理故事模式
        if self.story_mode:
            self.section_owner = 'Narrator'
            if self.section_idx == 0:
                with_end = False
            else:
                with_start = False
                with_end = False
            new_line = False

        if self.continuous_generation:
            new_line = False
            with_end = False

        debug_print('当前section owner:', self.section_owner)
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
                debug_print('未知的section owner！')
                section_name = self.section_owner
            debug_print('当前section name:', section_name)
            debug_print('no_next_line:', self.no_next_line)
            debug_print('continuous_generation:', self.continuous_generation)
            if section_name in self.pseudo_tags:
                section = section_name + ': ' + section
                section_name = self.pseudo_tags[section_name]
            section = self.make_block(section_name, section,
                                      with_start, with_end,
                                      new_line)
            debug_print('当前section:', section)

        return section

    def process_prompt(self, prompt: str):
        sections, current_section = [], []
        lines: list[str] = prompt.split('\n')
        line_count = len(lines)
        debug_print('当前行数:', line_count)
        for idx in range(line_count):
            debug_print('当前行:', idx)
            new_section = False
            section_owner_new = ''
            line = lines[idx]

            colon = line.find(':')
            if colon != -1:
                section_owner_new = line[:colon]
                line = line[colon + 1:]
                new_section = True

            # 处理忽略
            if self.user_tags.ignore_following in line:
                if new_section:
                    sections.append(
                        self.process_section(current_section))
                    current_section = []
                    self.section_owner = section_owner_new
                self.no_next_line = True
                self.continuous_generation = True
                line = line[:line.find(self.user_tags.ignore_following)]
                debug_print(line)
                current_section.append(line)
                sections.append(
                    self.process_section(current_section))
                current_section = []
                break

            if new_section:
                if self.section_start:
                    sections.append(
                        self.process_section(current_section))
                    self.section_idx += 1
                    current_section = []
                self.section_owner = section_owner_new
                self.section_start = True

            current_section.append(line)

            if idx == line_count - 1:
                self.continuous_generation = True

        if len(current_section) > 0:
            sections.append(
                self.process_section(current_section))
            current_section = []

        sections = '\n'.join(sections)
        if self.no_next_line:
            sections = sections.strip()

        return sections

    def switch_model(self, model_name: str, model_version: str | None = None):
        configs = list(
            filter(lambda x: x['model'] == model_name, self.config_file))
        if model_version is not None:
            config = list(
                filter(lambda x: x['version'] == model_version, configs))[0]
        else:
            config = configs[0]
        if len(config) == 0:
            raise Exception('未找到对应模型的配置文件！')
        self.user_tags.apply_config(config)

    def split_generated_string(self, generated: str):
        for end_tags in [self.user_tags.sys_end, self.user_tags.user_end,
                         self.user_tags.model_end, self.user_tags.other_end]:
            generated = generated.replace(end_tags, '<<<<||mark_here||>>>>')

        parts = generated.split('<<<<||mark_here||>>>>')
        debug_print('分割后的部分:', parts)

        if len(parts) == 1:
            return parts[0]

        for idx in range(len(parts)):
            owner, part = None, parts[idx]
            part = part.lstrip('\n ').rstrip()
            if part.startswith(self.user_tags.sys_start):
                owner = 'sys'
                part = part[len(self.user_tags.sys_start):].lstrip('\n ')
            elif part.startswith(self.user_tags.user_start):
                owner = 'user'
                part = part[len(self.user_tags.user_start):].lstrip('\n ')
            elif part.startswith(self.user_tags.model_start):
                owner = 'model'
                part = part[len(self.user_tags.model_start):].lstrip('\n ')
            elif self.user_tags.has_other and part.startswith(self.user_tags.other_start):
                part = part.split('\n')
                debug_print('other:', part)
                owner = part[0][len(self.user_tags.other_start):].lstrip(' ')
                part = '\n'.join(part[1:]).lstrip('\n ')
            if owner is not None:
                debug_print('owner:', owner)
                parts[idx] = owner + ': ' + part

        parts = '\n'.join(parts)
        return parts


prompt_template_state = TemplateHelper()


def llama_prompt_template(prompt, memory, version: str):
    prompt_template_state.switch_model('llama', version)

    ignore_following_tag = prompt_template_state.user_tags.ignore_following
    if ignore_following_tag in prompt:
        prompt = prompt[:prompt.rfind(
            ignore_following_tag) + len(ignore_following_tag)]

    if prompt_template_state.user_tags.story_mode in memory:
        # memory = '<|system|>\n你是专业的故事编写者，请根据用户输入内容续写故事<|end|>\n'
        # prompt_template_state.story_mode = True
        debug_print('进入故事模式')
    else:
        pass
    memory = prompt_template_state.make_block(
        'sys', memory.strip(), new_line=True) + '\n'

    prompt = prompt_template_state.process_prompt(prompt)
    prompt = prompt_template_state.user_tags.beginning + memory + prompt

    return prompt, ''


def phi3_prompt_template(prompt: str, memory: str):
    prompt_template_state.switch_model('phi',  'v3.5')

    ignore_following_tag = prompt_template_state.user_tags.ignore_following
    if ignore_following_tag in prompt:
        prompt = prompt[:prompt.rfind(
            ignore_following_tag) + len(ignore_following_tag)]

    if prompt_template_state.user_tags.story_mode in memory:
        # memory = '<|system|>\n你是专业的故事编写者，请根据用户输入内容续写故事<|end|>\n'
        # prompt_template_state.story_mode = True
        debug_print('进入故事模式')
    else:
        pass
    memory = '<|system|>\n' + memory + '<|end|>\n'

    prompt = prompt_template_state.process_prompt(prompt)
    prompt = prompt_template_state.user_tags.beginning + memory + prompt

    return prompt, ''


def qwen_prompt_template(prompt: str, memory: str):
    if prompt_template_state.user_tags.ignore_following in prompt:
        prompt = prompt[:prompt.rfind(
            prompt_template_state.user_tags.ignore_following)]
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

    prompt = prompt_template_state.user_tags.beginning + prompt

    return prompt, ''


def normal_prompt_template(prompt: str, memory: str,
                           subtype: str, subversion = None):
    # assert subtype in ['yi', 'qwen', 'chatglm', 'yi', 'mistral', "dolphin"]
    prompt_template_state.switch_model(subtype, subversion)

    ignore_following_tag = prompt_template_state.user_tags.ignore_following
    if ignore_following_tag in prompt:
        prompt = prompt[:prompt.rfind(
            ignore_following_tag) + len(ignore_following_tag)]
        debug_print('改变的prompt: ', prompt)

    system = ''
    if prompt_template_state.user_tags.story_mode in memory:
        memory = ''
        system = prompt_template_state.make_block(
            'sys', '以下内容是中篇小说', new_line=True)
        prompt_template_state.story_mode = True
    else:
        if memory.startswith('System:'):
            system, memory = memory[7:].split(prompt_template_state.user_tags.memory_splitter)
            system = prompt_template_state.make_block(
                'sys', system, new_line=True)
        if memory.strip() != '':
            memory = prompt_template_state.make_block(
                'memory', memory.strip(), new_line=True)

    prompt = prompt_template_state.process_prompt(prompt)
    prompt = prompt_template_state.user_tags.beginning + system + '\n' + prompt

    last_pos = prompt.rfind(prompt_template_state.user_tags.other_end)
    last_pos = last_pos + len(prompt_template_state.user_tags.other_end)
    if prompt[last_pos] == '\n':
        if prompt[last_pos + 1] == '\n':
            last_pos += 2
        else:
            last_pos += 1
    prompt = prompt[:last_pos] + (memory + '\n' if memory.strip() != '' else '') + prompt[last_pos:]

    return prompt, ''


ENABLE_TEMPLATE_PROCESSING = True


def prompt_template(prompt, memory):
    if not ENABLE_TEMPLATE_PROCESSING:
        print('模板处理已禁用')
        return prompt, memory
    global prompt_template_state
    prompt_template_state = TemplateHelper()
    print('进入提示词模板生成函数')
    prompt, memory = normal_prompt_template(prompt, memory, 'llama', 'nsfw')
    print('生成的提示词完毕\n')
    return prompt, memory


def out_post_process(outstr: str):
    if not ENABLE_TEMPLATE_PROCESSING:
        return outstr

    print('\n\n======进入输出后处理函数======')
    print('------输出前------')
    print(outstr)
    print('------输出后------')

    if prompt_template_state.story_mode:
        outstr = '\r' + outstr
    outstr = prompt_template_state.split_generated_string(outstr)

    print(outstr)
    print('======输出后处理完毕======\n\n')
    return outstr
