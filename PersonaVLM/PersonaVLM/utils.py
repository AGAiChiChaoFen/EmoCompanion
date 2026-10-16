
import math
import uuid
import random
from datetime import datetime, timedelta


def cosine_decay_factor(current_step, total_steps=50, start_val=0.5, end_val=0.1):
    if current_step > total_steps:
        current_step = total_steps
    progress = current_step / total_steps
    cosine_value = math.cos(progress * math.pi)
    normalized_value = (cosine_value + 1) / 2.0
    factor = end_val + (start_val - end_val) * normalized_value
    return 1 - factor


def generate_64bit_id():
    '''Generate a unique ID using UUID version 4 (randomly generated numbers), and truncating it to the first 64 bits.'''
    full_uuid = uuid.uuid4().int
    return full_uuid & 0xFFFFFFFFFFFFFFFF


def is_time_diff_over_minutes(time1, time2, threshold_minutes):
    '''Check if two times are more than threshold_minutes apart'''
    if time1 is None or time2 is None:
        return True
    time_format = "%Y-%m-%d %H:%M"
    t1 = datetime.strptime(time1, time_format)
    t2 = datetime.strptime(time2, time_format)
    
    diff_minutes = abs((t2 - t1).total_seconds()) / 60
    return diff_minutes > threshold_minutes


def datetime_add_minutes(time_str, minutes_to_add=180, time_format="%Y-%m-%d %H:%M"):
    '''Adds minutes to given date string'''
    if time_str is None:
        return None
    dt = datetime.strptime(time_str, time_format) + timedelta(minutes=minutes_to_add)
    return dt.strftime(time_format)


def datetime_add_days(time_str, days_to_add=1, time_format="%Y-%m-%d %H:%M"):
    '''Adds days to given date string'''
    dt = datetime.strptime(time_str, time_format) + timedelta(days=days_to_add)
    return dt.strftime(time_format)


def compare_time_strings(time_str1, time_str2, time_format="%Y-%m-%d %H:%M"):
    '''
    return
        -1: time_str1 < time_str2
         0: time_str1 == time_str2
         1: time_str1 > time_str2
    '''
    if time_str1 is None or time_str2 is None:
        return 0
    dt1 = datetime.strptime(time_str1, time_format)
    dt2 = datetime.strptime(time_str2, time_format)

    if dt1 < dt2:
        return -1
    elif dt1 > dt2:
        return 1
    else:
        return 0


def is_time_in_range(start_time_str, end_time_str, time_to_check_str, time_format="%Y-%m-%d %H:%M"):
    '''Checks whether a specific time falls within a range of times'''
    start_dt = datetime.strptime(start_time_str, time_format)
    end_dt = datetime.strptime(end_time_str, time_format)
    check_dt = datetime.strptime(time_to_check_str, time_format)
    return start_dt <= check_dt <= end_dt


def get_current_time(time_format="%Y-%m-%d %H:%M"):
    now = datetime.now()
    return now.strftime(time_format)

def json_to_txt(content, remove_time=False):
    if remove_time and 'start_time' in content and 'end_time' in content:
        del content['start_time']
        del content['end_time']
    # print(content)
    ans = []
    if isinstance(content, list):
        for item in content:
            ans.append(json_to_txt(item, remove_time=remove_time))
    else:
        for key in content:
            if isinstance(content[key], dict):
                ans.append(json_to_txt(content[key]))
            else:
                if isinstance(content[key], list):
                    tmp = ','.join([str(i) for i in content[key]])
                    ans.append(f"\"{key}\": {tmp}")
                else:
                    if content[key] is None:
                        tmp = 'null'
                    else:
                        tmp = str(content[key])
                    ans.append(f"\"{key}\": {tmp}")
    return '\n'.join(ans)

def parse_reasoning_output(output, query, force_retrieve=False):
    # think, action, resposne, retrieve
    ans = {}
    try:
        ans["think"] = output.split('<think>')[1].split('</think>')[0].strip()
        if '<retrieve>' in output and '</retrieve>' in output:
            ans["action"] = 'retrieve'
        else:
            ans["action"] = 'answer'
        if ans["action"] == "retrieve":
            ans["response"] = ""
            retrieve_info = {}
            retrieve_info["keywords"] = output.split('"keywords":')[1].split('"start_time":')[0].strip().strip('"')
            start_time = output.split('"start_time":')[1].split('"end_time"')[0].strip().strip('"')
            end_time = output.split('"end_time":')[1].split('</retrieve>')[0].strip().strip('"')
            start_time = validate_datetime(start_time)
            end_time = validate_datetime(end_time)
            if start_time and end_time and compare_time_strings(start_time, end_time) > 0:
                start_time = end_time = None
            retrieve_info["start_time"] = start_time
            retrieve_info["end_time"] = end_time
            retrieve_info["retrieve"] = True
            ans["retrieve_info"] = retrieve_info 
        else:
            ans["response"] = output.split('<answer>')[1].split('</answer>')[0].strip()
            ans["retrieve_info"] = {}
    except:
        print("parse reasoning output error: ", output)
        if "<answer>" in output and '</answer>' in output:
            ans["think"] = ""
            ans["action"] = "answer"
            ans["response"] = output.split('<answer>')[1].split('</answer>')[0].strip()
            ans["retrieve_info"] = {}
        else:
            ans["think"] = ""
            ans["action"] = "retrieve"
            ans["response"] = ""
            ans["retrieve_info"] = {"keywords": query["query"], "start_time": None, "end_time": None, "retrieve": True}

    if ans["retrieve_info"] == {} and force_retrieve:
        ans["retrieve_info"] = {"keywords": query["query"], "start_time": None, "end_time": None, "retrieve": True}
        ans["action"] = "retrieve"
    return ans

def personality_info_to_json(query, personality_info):
    try:
        assert '"openness":' in personality_info
        assert '"conscientiousness":' in personality_info
        assert '"extraversion":' in personality_info
        assert '"agreeableness":' in personality_info
        assert '"neuroticism":' in personality_info
        
        openness = int(personality_info.split('"openness":')[1].split('"conscientiousness"')[0].strip().strip('"'))
        conscientiousness = int(personality_info.split('"conscientiousness":')[1].split('"extraversion"')[0].strip().strip('"'))
        extraversion = int(personality_info.split('"extraversion":')[1].split('"agreeableness"')[0].strip().strip('"'))
        agreeableness = int(personality_info.split('"agreeableness":')[1].split('"neuroticism"')[0].strip().strip('"'))
        neuroticism = int(personality_info.split('"neuroticism":')[1].strip().strip('"'))

        scores = [1, 2, 3, 4, 5]
        return {
            "openness": openness if openness in scores else 3,
            "conscientiousness": conscientiousness if conscientiousness in scores else 3,
            "extraversion": extraversion if extraversion in scores else 3,
            "agreeableness": agreeableness if agreeableness in scores else 3,
            "neuroticism": neuroticism if neuroticism in scores else 3
        }
    except:
        print("Error parsing personality info: {}".format(personality_info))
        return {
            "openness": 3,
            "conscientiousness": 3,
            "extraversion": 3,
            "agreeableness": 3,
            "neuroticism": 3,
        }
    
def semantic_memory_to_json(semantic_memory):
    try:
        assert '"reason":' in semantic_memory
        assert '"decision":' in semantic_memory
        assert '"content":' in semantic_memory
        assert '"keywords":' in semantic_memory

        reason = semantic_memory.split('"reason":')[1].split('"decision"')[0].strip().strip('"')
        decision = True if "true" in semantic_memory.split('"decision":')[1].split('"content"')[0].lower() else False
        content = semantic_memory.split('"content":')[1].split('"keywords"')[0].strip().strip('"') if decision else ""
        keywords = semantic_memory.split('"keywords":')[1].strip().strip('"') if decision else ""

        return {
            "reason": reason,
            "decision": decision,
            "content": content,
            "keywords": keywords
        }
    except:
        # raise Exception(f"Something wrong in key memory: {semantic_memory}")
        print("Error parsing semantic memory: {}".format(semantic_memory))
        return {
            "reason": "",
            "decision": False,
            "content": "",
            "keywords": ""
        }


def topics_to_json(topics, N):
    try:
        assert "topic_summary" in topics and "keywords" in topics and "source_dialog_indices" in topics
        cnotents = topics.split('"topic_summary":')[1:]
        ans = []
        all_indices = []
    except:
        print('Error in parsing:', topics, N)
        return [{
            "topic_summary": topics,
            "keywords": topics,
            "source_dialog_indices": list(range(N))
        }]
    for content in cnotents:
        try:
            topic_summary = content.split('"keywords"')[0].strip().strip('"')
            keywords = content.split('"keywords":')[1].split('"source_dialog_indices"')[0].strip().strip('"').strip('[').strip(']').strip()
            source_dialog_indices = content.split('"source_dialog_indices":')[1].strip().replace("[]", "").strip(',').strip('"').strip('[').strip(']').strip()
            if source_dialog_indices:
                source_dialog_indices = [int(i.strip()) for i in source_dialog_indices.replace(", ", ',').replace(" ", ',').split(',')]
                source_dialog_indices = [i for i in source_dialog_indices if i >= 0 and i < N]
            else:
                source_dialog_indices = [N-1]
            all_indices.extend(source_dialog_indices)
            ans.append({
                    "topic_summary": topic_summary,
                    "keywords": keywords,
                    "source_dialog_indices": source_dialog_indices
                })
        except:
            print(f"something wrong in parsing topics: {content}")
            continue
    # print(topics, all_indices, ans)
    if len(ans) == 0:
        return [{
            "topic_summary": topics,
            "keywords": topics,
            "source_dialog_indices": list(range(N))
        }]

    missed_indice = list(set(range(N)) - set(all_indices))
    if missed_indice:
        ans[0]["source_dialog_indices"].extend(missed_indice)

    result = []
    for tmp in ans:
        if tmp["source_dialog_indices"]:
            tmp["source_dialog_indices"] = sorted(tmp["source_dialog_indices"])
            result.append(tmp)
    return result
    

def profile_to_json(profile, ori_profile):
    ans = {}
    dict_key = []
    for key in ori_profile.keys():
        if isinstance(ori_profile[key], dict):
            dict_key.append(key)
            ans[key] = {}
    # parse all attributes
    contents = profile.split('\n')
    for content in contents:
        if ':' in content:
            key = content.split(':')[0].strip().strip('"')
            value = content.split(':')[1].strip().strip(',').strip('"')
            if key and value:
                if key not in ans:
                    ans[key] = value
    ans["name"] = ori_profile["name"]
    return ans

def procedural_to_json(update_procedural):
    ProceduralMemory = {}
    for line in update_procedural.split("\n"):
        if '":' in line:
            key = line.split('":')[0].strip().strip('"')
            value = line.split(":")[1].strip().strip('"')
            ProceduralMemory[key] = value
    return ProceduralMemory

def validate_datetime(s):
    try:
        if not s:
            return None
        datetime.strptime(s, '%Y-%m-%d %H:%M')
        return s
    except ValueError:
        return None

def maybe_reduce_profile(profile, p=0.5):
    if random.random() < p:
        keys = list(profile.keys())
        if "name" in keys:
            keys.remove("name")  # 保留"name"
        random.shuffle(keys)
        keep_num = random.randint(0, 2)
        keepkeys = keys[:keep_num]
        drop_keys = [k for k in keys if k not in keepkeys]
        for k in drop_keys:
            del profile[k]
    
    return profile


def random_datetime(start="2024-01-01 00:00", end="2025-12-31 23:59", fmt="%Y-%m-%d %H:%M"):
    stime = datetime.strptime(start, fmt)
    etime = datetime.strptime(end, fmt)
    td = etime - stime
    random_seconds = random.randint(0, int(td.total_seconds()))
    rtime = stime + timedelta(seconds=random_seconds)
    return rtime.strftime(fmt)


def get_weekday(date_str, lang='en'):
    weekdays_en = ["Monday", "Tuesday", "Wednesday", "Thursday",
                   "Friday", "Saturday", "Sunday"]
    weekdays_zh = ["星期一", "星期二", "星期三", "星期四",
                   "星期五", "星期六", "星期日"]
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    idx = dt.weekday()
    if lang == 'en':
        return weekdays_en[idx]
    elif lang == 'zh':
        return weekdays_zh[idx]
    else:
        raise ValueError("lang parameter only supports 'en' or 'zh")



