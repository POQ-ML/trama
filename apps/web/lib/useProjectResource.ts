"use client";
import { useEffect, useState } from 'react';
import { request } from './discovery';
import { projectMessage } from './projects';
/** Each path has its own cancellable read. Loaded data survives retryable failures. */
export function useProjectResource<T>(path: string) {
  const [state,setState] = useState<{path:string;data:T|null;error:string|null;loading:boolean}>({path,data:null,error:null,loading:true});
  const [revision,setRevision] = useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    setState(old=>({path,data:old.path===path ? old.data : null,error:null,loading:true}));
    void request<T>(path,controller.signal).then(data=>{if(!controller.signal.aborted)setState({path,data,error:null,loading:false});}).catch(error=>{if(!controller.signal.aborted)setState(old=>({...old,error:projectMessage(error),loading:false}));});
    return ()=>controller.abort();
  },[path,revision]);
  return {data:state.path===path ? state.data : null,error:state.path===path ? state.error : null,loading:state.path!==path || state.loading,refresh:()=>setRevision(v=>v+1)};
}
