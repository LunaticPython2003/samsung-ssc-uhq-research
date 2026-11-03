import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;

/** Inspect Samsung SSC -> A2DP HAL configuration conversion locally.
    Never upload vendor decompilation logs to the repository. */
public class AuditSscToHalConfig extends GhidraScript {
 public void run() throws Exception {
   DecompInterface d=new DecompInterface();
   d.openProgram(currentProgram);
   int named=0, matched=0;
   for(Function f: currentProgram.getFunctionManager().getFunctions(true)){
     String name=f.getName();
     if(name.toLowerCase().contains("ssc")) {
       if(named < 140) println("SSC_NAME "+f.getEntryPoint()+" "+name);
       named++;
     }
     if(name.contains("SscToHalConfig")||name.contains("SscCodecTo")||
        name.contains("A2dpSsc")||name.contains("GetBitRateSsc")||
        name.contains("AdjustCodecSsc")){
       println("\n## DECOMP "+f.getEntryPoint()+" "+name);
       DecompileResults r=d.decompileFunction(f,85,monitor);
       if(r!=null&&r.decompileCompleted()&&r.getDecompiledFunction()!=null){
         String body=r.getDecompiledFunction().getC();
         println(body.substring(0,Math.min(26000,body.length())));
       } else println("FAILED");
       matched++;
     }
   }
   println("SSC_TOTAL_NAMES "+named+" TARGETS "+matched);
   d.dispose();
 }
}