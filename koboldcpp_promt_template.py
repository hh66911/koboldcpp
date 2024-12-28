import re


def debug_print(*args, **kwargs):
    return
    print(*args, **kwargs)
    print('-' * 100)


class UserDefinedTags:
    def __init__(self) -> None:
        self.ignore_following = '<IgnoreFollowing>'
        self.no_new_section = '<ContinueSection>'
        self.comment_start = '<Comment>'
        self.comment_end = '</Comment>'
        self.memory_splitter = '-|-|-'

        self.alias_tag = re.compile(r'<Alias:([\w\s]+)-([\w\s]+)>')
        self.pseudo_tag = re.compile(r'<Pseudo:([\w\s,]+)-([\w\s]+)>')

        self.reserved_owners = [
            'sys', 'user', 'model'
        ]
        self.local_alias_tags = {
            '<Alias/sys>': 'sys',
            '<Alias/user>': 'user',
            '<Alias/model>': 'model'
        }
        self.local_pseudo_tags = {
            '<Pseudo/sys>': 'sys',
            '<Pseudo/user>': 'user',
            '<Pseudo/model>': 'model',
            '<Pseudo/>': ''
        }

        self.has_other = False

    def apply_config(self, config: dict):
        self.header_postfix = config['header_postfix'] if 'header_postfix' in config else ''
        self.end_prefix = config['end_prefix'] if 'end_prefix' in config else ''

        self.beginning = config['beginning'] if 'beginning' in config else ''

        post_fix_disable = [] if 'disable_postfix' not in config else config['disable_postfix']
        self.sys_start = config['sys_start'] + (self.header_postfix if 'sys' not in post_fix_disable else '')
        self.sys_end = self.end_prefix + (config['sys_end'] if 'sys_end' in config else '')
        self.user_start = config['user_start'] + (self.header_postfix if 'user' not in post_fix_disable else '')
        self.user_end = self.end_prefix + (config['user_end'] if 'user_end' in config else '')
        self.model_start = config['model_start'] + (self.header_postfix if 'model' not in post_fix_disable else '')
        self.model_end = self.end_prefix + (config['model_end'] if 'model_end' in config else '')
        self.mem_start = config['mem_start'] if 'mem_start' in config else '' # mem don't have header postfix
        self.mem_end = self.end_prefix + (config['mem_end'] if 'mem_end' in config else '')

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


class ContentBlock:
    def __init__(self, start: str, content: str,
                 end: str, new_line=False) -> None:
        self.start = start
        self.content = content
        self.end = end
        self.new_line = new_line
        
    def __str__(self) -> str:
        return self.start + self.content + self.end + ('\n' if self.new_line else '')
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def front_insert(self, new_content: str):
        new_content += self.content
        return ContentBlock(self.start, new_content,
                            self.end, self.new_line)
        
    def back_insert(self, new_content: str):
        new_content  = self.content + new_content
        return ContentBlock(self.start, new_content,
                            self.end, self.new_line)
        
    def strip(self):
        return ContentBlock(self.start, self.content.strip(),
                            self.end, self.new_line)


class TemplateHelper:
    def __init__(self, model = None, version = None) -> None:
        self.continuous_generation = False
        self.no_next_line = False
        self.story_mode = False

        self.user_tags = UserDefinedTags()
        
        self.current_config: dict|None = None
        self.available_configs = []
        self.lock_config = False

        import json
        with open("tkn_configs.json", 'r', encoding='utf-8') as f:
            self.config_file = json.load(f)
            
        for c in self.config_file:
            self.available_configs.append(
                (c['model'], c['version'] if 'version' in c else '')
                )

        if model is None:
            self.switch_model('llama')
        else:
            self.switch_model(model, version)

        self.comment_on = False
        self.section_start = False
        self.paragraph_start = False

        self.section_owner = ''
        self.section_idx = 0
        self.allow_strip_section = True

        self.user_alias = None
        self.model_alias = None
        self.sys_alias = None
        
        self.local_alias = None
        self.local_pseudo = None
        
        self.pseudo_tags = dict()
        
    def reset_local_states(self):
        self.local_alias = None
        self.local_pseudo = None
        

    def make_block(self, name: str, content: str,
                   with_start=True, with_end=True,
                   new_line=False) -> ContentBlock:
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
            case 'mem':
                start = self.user_tags.mem_start
                end = self.user_tags.mem_end
            case _:
                start = self.user_tags.other_start +\
                    name + self.user_tags.other_postfix
                end = self.user_tags.other_end

        if not with_start:
            start = ''
        if not with_end:
            end = ''

        return ContentBlock(start, content, end, new_line)

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

    def process_section(self, cur_section: list[str]
                        ) -> tuple[ContentBlock | str, bool]:
        section = ''
        self.allow_strip_section = True
        debug_print('当前section:', cur_section)
        if len(self.section_owner) > 0:
            debug_print('原始section owner:', self.section_owner)
        else:
            debug_print('未指定section owner！')

        for line in cur_section:
            for tag, value in self.user_tags.local_alias_tags.items():
                if tag in line:
                    self.local_alias = value
                    line = line.replace(tag, '')
            for tag, value in self.user_tags.local_pseudo_tags.items():
                if tag in line:
                    self.local_pseudo = value
                    line = line.replace(tag, '')

            section += self.process_paragraph(line)

        if self.allow_strip_section:
            section = section.strip()

        with_start, with_end = True, True
        new_line = True

        if self.continuous_generation:
            new_line = False
            with_end = False

        is_block = False
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
                
            if self.local_pseudo is not None:
                section = self.section_owner + ': ' + section
                if self.local_pseudo != '':
                    section_name = self.local_pseudo
            elif self.section_owner in self.pseudo_tags:
                section = self.section_owner + ': ' + section
                section_name = self.pseudo_tags[self.section_owner]
                
            if self.local_alias is not None:
                section_name = self.local_alias
                
            debug_print('当前section name:', section_name)
            debug_print('no_next_line:', self.no_next_line)
            debug_print('continuous_generation:', self.continuous_generation)
            section = self.make_block(section_name, section,
                                      with_start, with_end,
                                      new_line)
            is_block = True
            
            debug_print('当前section:', section)
            self.reset_local_states()

        return (section, is_block)

    def process_prompt(self, prompt: str):
        sections: list[tuple[ContentBlock | str, bool]] = []
        current_section = []
        lines: list[str] = prompt.split('\n')
        line_count = len(lines)
        debug_print('当前行数:', line_count)
        for idx in range(line_count):
            debug_print('当前行:', idx)
            new_section = False
            section_owner_new = ''
            line = lines[idx]
            
            # 处理注释
            if self.user_tags.comment_end in line and self.comment_on:
                self.comment_on = False
                line = line[line.find(
                    self.user_tags.comment_end) + len(self.user_tags.comment_end):]
            if self.comment_on:
                continue
                    
            if self.user_tags.comment_start in line:
                if self.user_tags.comment_end in line:
                    left = line[:line.find(self.user_tags.comment_start)]
                    right = line[line.find(self.user_tags.comment_end) + len(self.user_tags.comment_end):]
                    line = left + right
                else:
                    self.comment_on = True
                    line = line[:line.find(self.user_tags.comment_start)]
                debug_print('触发 <Comment> line: ', line)

            # 处理忽略
            if self.user_tags.ignore_following in line:
                if new_section:
                    sections.append(
                        self.process_section(current_section))
                    self.section_idx += 1
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

            if self.user_tags.no_new_section in line:
                new_section = False
                line = line.replace(self.user_tags.no_new_section, '')
            else:
                colon = line.find(':')
                if colon != -1 and colon < 50:
                    section_owner_new = line[:colon]
                    line = line[colon + 1:]
                    new_section = True

            if new_section:
                # 第一个 section
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

        if self.no_next_line:
            sections[0] = (sections[0][0].strip(), sections[0][1])
            sections[-1] = (sections[-1][0].strip(), sections[-1][1])
            
        debug_print('处理后的sections:', sections)

        blocks: list[ContentBlock] = []
        for se in sections:
            if se[1]:
                blocks.append(se[0])
            else:
                blocks[-1] = blocks[-1].back_insert(se[0])

        return blocks

    def switch_model(self, model_name: str, model_version: str | None = None):
        if self.lock_config:
            raise Exception('配置文件被锁定！')
        configs = list(
            filter(lambda x: x['model'] == model_name, self.config_file))
        if model_version is not None:
            config = list(
                filter(lambda x: x['version'] == model_version, configs))[0]
        else:
            config = configs[0]
        if len(config) == 0:
            raise Exception('未找到对应模型的配置文件！')
        self.current_config = config
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


def normal_prompt_template(state: TemplateHelper, prompt: str, memory: str, subtype = None,
                           subversion = None):
    # assert subtype in ['yi', 'qwen', 'chatglm', 'yi', 'mistral', "dolphin"]
    if subtype is not None:
        state.switch_model(subtype, subversion)

    ignore_following_tag = state.user_tags.ignore_following
    if ignore_following_tag in prompt:
        prompt = prompt[:prompt.rfind(
            ignore_following_tag) + len(ignore_following_tag)]
        debug_print('改变的prompt: ', prompt)

    system = ''
    if memory.startswith('System:'):
        system, memory = memory[7:].split(state.user_tags.memory_splitter)
        system = state.make_block(
            'sys', system, new_line=True)
    if memory.strip() != '':
        memory = str(state.make_block(
            'mem', memory.strip(), new_line=True))

    blocks = state.process_prompt(prompt)
    debug_print('组合后的blocks:', blocks)

    if system.strip() != '':
        system = state.user_tags.beginning + str(system) + '\n'
    else:
        system = ''
        
    if memory.strip() != '':
        blocks[-2] = blocks[-2].front_insert(memory)
    prompt = system + '\n'.join(map(str, blocks))

    return prompt, ''


ENABLE_TEMPLATE_PROCESSING = True


def prompt_template(prompt, memory, modelname, modelversion):
    if not ENABLE_TEMPLATE_PROCESSING:
        print('模板处理已禁用')
        return prompt, memory
    print(f'正在使用模板名：{modelname}，版本：{modelversion}')
    state = TemplateHelper(modelname, modelversion)
    print('进入提示词模板生成函数')
    prompt, memory = normal_prompt_template(state, prompt, memory)
    print('生成的提示词完毕\n')
    return prompt, memory, state


def out_post_process(outstr: str, state: TemplateHelper):
    if not ENABLE_TEMPLATE_PROCESSING:
        return outstr

    print('\n\n======进入输出后处理函数======')
    print('------输出前------')
    print(outstr)
    print('------输出后------')

    # if state.story_mode:
    #     outstr = '\r' + outstr
    # outstr = state.split_generated_string(outstr)
    if outstr.strip().endswith(state.user_tags.model_end):
        outstr = outstr.strip()[:-len(state.user_tags.model_end)]

    print(outstr)
    print('======输出后处理完毕======\n\n')
    return outstr
