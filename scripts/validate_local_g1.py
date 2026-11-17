"""Explicit synthetic-only local G1 validation; never reads owner memory.
Run with python -m scripts.validate_local_g1 after approved model setup.
"""

def main():
    import os,sys,json,time,resource,math,tempfile,hashlib
    sys.path.insert(0,os.getcwd())
    import db,memory,memory_embeddings as embeddings
    from local_model_lifecycle import memory_status
    import requests
    import subprocess,threading
    samples=[]
    stop=threading.Event()
    def sample():
     while not stop.is_set():
      try:
       lines=subprocess.check_output(['ps','-axo','rss=,comm='],text=True).splitlines()
       rss=sum(int(line.split(None,1)[0])*1024 for line in lines if any(name in line.lower() for name in ('ollama','mlx_lm','mlx-engine')))
       samples.append(rss)
      except (OSError,subprocess.SubprocessError): pass
      stop.wait(.2)
    monitor=threading.Thread(target=sample,daemon=True)
    monitor.start()
    start=time.perf_counter();cpu=time.process_time();before=memory_status()
    client=embeddings.OllamaEmbeddingClient()
    records=[('The astronomy club studies stars and galaxies.','Which group observes galaxies?'),('The kitchen serves fresh bread and soup.','Where can I eat soup?'),('المكتبة تفتح يوم الاثنين لاستعارة الكتب.','أين أستطيع استعارة الكتب؟')]
    vectors=client.embed_documents([x[0] for x in records]);queries=client.embed_query([x[1] for x in records]);rankings=[]
    for i,q in enumerate(queries):
     scores=[embeddings.cosine_similarity(q,d) for d in vectors];rankings.append({'query':records[i][1],'scores':scores,'top':max(range(len(scores)),key=scores.__getitem__),'expected':i})
    with tempfile.TemporaryDirectory(prefix='oracle-synthetic-') as directory:
     db.DB_PATH=os.path.join(directory,'synthetic.db')
     for text,_ in records:memory.write_memory(text,'fact','synthetic:one','synthetic-validation')
     memory.write_memory('Secret synthetic other tenant astronomy fact','fact','synthetic:two','synthetic-validation')
     indexed=embeddings.index_memory_scope('synthetic:one',client=client,batch_size=2,max_records=3)
     repeated=embeddings.index_memory_scope('synthetic:one',client=client,batch_size=2,max_records=3)
     other=embeddings.index_memory_scope('synthetic:two',client=client,batch_size=2,max_records=3)
     matches=embeddings.retrieve_vector_matches('synthetic:one',records[0][1],client=client)
     isolated=all('other tenant' not in str(x.record) for x in matches)
     tags=requests.get('http://127.0.0.1:11434/api/tags',proxies={'http':'','https':''},timeout=5).json()
     loaded=requests.get('http://127.0.0.1:11434/api/ps',proxies={'http':'','https':''},timeout=5).json()
    stop.set();monitor.join(timeout=2)
    result={'sampled_ollama_related_peak_rss_bytes':max(samples,default=0),'sample_count':len(samples),'model':client.model_name,'dimensions':sorted({len(v) for v in vectors+queries}),'all_finite':all(math.isfinite(x) for v in vectors+queries for x in v),'rankings':rankings,'index_result':indexed,'repeat_index_result':repeated,'other_scope_index_result':other,'scope_isolated':isolated,'retrieval_count':len(matches),'seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu,'python_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'pressure_before':before,'pressure_after':memory_status(),'loaded_after':loaded,'model_tags':[x for x in tags['models'] if x['name']==client.model_name]}
    result['passed'] = (result['dimensions'] == [768] and result['all_finite'] and all(row['top'] == row['expected'] for row in rankings) and indexed['indexed_count'] == 3 and repeated['skipped_count'] == 3 and other['indexed_count'] == 1 and isolated and len(matches) > 0 and not loaded.get('models'))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['passed'] else 1


if __name__ == "__main__":
    raise SystemExit(main())
