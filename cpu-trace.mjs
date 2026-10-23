import fs from 'node:fs/promises';
import {realpathSync} from 'node:fs';
import path from 'node:path';
import cp from 'node:child_process';
import {syncBuiltinESMExports} from 'node:module';
const relevant = value => String(value).includes('best-agent-cpu-');
for (const name of ['realpath','stat']) {
  const original=fs[name];
  fs[name]=async function(...args) {
    try {
      const value=await original.apply(this,args);
      if(relevant(args[0])) console.error('PATH_TRACE',JSON.stringify({op:name,path:String(args[0]),value:name==='stat'?{directory:value.isDirectory()}:String(value),...(name==='realpath'?{sync:realpathSync(args[0]),native:realpathSync.native(args[0])}:{})}));
      return value;
    } catch(error) {if(relevant(args[0])) console.error('PATH_TRACE',JSON.stringify({op:name,path:String(args[0]),error:String(error)}));throw error;}
  };
}
const relative=path.relative;
path.relative=(from,to)=>{const value=relative(from,to);if(relevant(from)||relevant(to))console.error('PATH_TRACE',JSON.stringify({op:'relative',from,to,value}));return value;};
const spawn=cp.spawnSync;
cp.spawnSync=(file,args,options)=>{const result=spawn(file,args,options);if(String(file).includes('cpu-supervisor')&&String(args?.[0]).startsWith('--prepare'))console.error('PATH_TRACE',JSON.stringify({op:'prepare',file,args,status:result.status,error:result.error?.message,stderr:String(result.stderr||'')}));return result;};
syncBuiltinESMExports();
