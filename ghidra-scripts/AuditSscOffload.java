import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;

/** Targeted Samsung AIDL SSC offload validator audit; output remains local. */
public class AuditSscOffload extends GhidraScript {
    public void run() throws Exception {
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        int count=0;
        for(Function f : currentProgram.getFunctionManager().getFunctions(true)){
            String n=f.getName();
            if (f.isThunk() || !(n.contains("IsOffloadSscConfigurationValid")
                     || n.contains("GetA2dpOffloadCodecCapabilities"))) continue;
            println("### OFFLOAD_FUNCTION " + n + " @ " + f.getEntryPoint());
            DecompileResults r = decomp.decompileFunction(f,90,monitor);
            if(r != null && r.decompileCompleted() && r.getDecompiledFunction() != null) {
               String body = r.getDecompiledFunction().getC();
               println(body.substring(0, Math.min(body.length(),26000)));
            } else println("DECOMP_FAILED");
            count++;
        }
        decomp.dispose();
        println("TOTAL_AUDITED_OFFLOAD_FUNCTIONS "+count);
    }
}
