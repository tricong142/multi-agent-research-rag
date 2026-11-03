"""One diagnostic event per attempted generation, including pre-generation failure."""
import time


def generate_json(self,messages,*,max_new_tokens):
    import torch
    from .judge import extract_json_object,ModelOutputError
    text,parsed,error=None,None,None
    prompt_length=None;generated=None;phase='tokenize';timings={};tick=time.perf_counter()
    self._decode_prompt_length=None;self._decode_generated_lower_bound=0
    self.decoding_metadata={}
    try:
        rendered=self.tokenizer.apply_chat_template(list(messages),tokenize=False,add_generation_prompt=True)
        inputs=self.tokenizer(rendered,return_tensors='pt')
        prompt_length=inputs['input_ids'].shape[1];self._decode_prompt_length=prompt_length
        device=getattr(self.model,'device',None)
        if device is not None:inputs={key:value.to(device) for key,value in inputs.items()}
        timings[phase]=(time.perf_counter()-tick)*1000;phase='schema';tick=time.perf_counter()
        options=self.generation_options(messages)
        timings[phase]=(time.perf_counter()-tick)*1000;phase='generate';tick=time.perf_counter()
        with torch.inference_mode():
            ids=self.model.generate(**inputs,max_new_tokens=max_new_tokens,do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,**options)
        generated=len(ids[0])-prompt_length
        text=self.tokenizer.decode(ids[0][prompt_length:],skip_special_tokens=True)
        timings[phase]=(time.perf_counter()-tick)*1000;phase='parse';tick=time.perf_counter()
        try:parsed=extract_json_object(text)
        except ValueError as exc:raise ModelOutputError(str(exc),text) from exc
        return parsed
    except BaseException as exc:
        error=type(exc).__name__
        raise
    finally:
        timings[phase]=(time.perf_counter()-tick)*1000
        if self.on_generation is not None:
            self.on_generation({'event':'factchecker_generation','raw_output':text,
                'json_valid':parsed is not None,'parse_error_type':error,
                'parsed_keys':sorted(parsed) if parsed is not None else [],
                'prompt_tokens':prompt_length,'generated_tokens':generated,
                'generated_tokens_lower_bound':generated if generated is not None else self._decode_generated_lower_bound,
                'usage_complete':generated is not None,'failure_phase':phase if error else None,
                'phase_timings_ms':{key:round(value,3) for key,value in timings.items()},
                'max_new_tokens':max_new_tokens,**self.decoding_metadata})
