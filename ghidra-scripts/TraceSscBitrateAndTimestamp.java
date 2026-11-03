import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;

public class TraceSscBitrateAndTimestamp extends GhidraScript {
    public void run() throws Exception {
        String[] wanted = {
            "SscBitrateByBusyLevel",
            "A2DP_VendorGetPacketTimestampSsc",
            "A2DP_VendorCodecInfoStringSsc",
            "A2DP_VendorAdjustCodecSsc",
            "A2DP_VendorGetSscType",
            "A2DP_VendorGetTrackBitrateLimitationSsc"
        };
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        int n=0;
        for(Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            if(f.isThunk()) continue;
            String name=f.getName();
            for(String w : wanted) {
                if(name.contains(w)) {
                    DecompileResults result=decomp.decompileFunction(f,90,monitor);
                    println("\n==== FUNCTION "+name+" @ "+f.getEntryPoint()+" ====");
                    if(result != null && result.decompileCompleted() && result.getDecompiledFunction()!=null) {
                        String code=result.getDecompiledFunction().getC();
                        println(code.substring(0,Math.min(code.length(),28000)));
                    } else {
                        println("DECOMPILATION_ERROR: "+(result==null?"null":result.getErrorMessage()));
                    }
                    n++;
                    break;
                }
            }
        }
        println("DECOMPILED_TARGET_COUNT "+n);
        decomp.dispose();
    }
}
