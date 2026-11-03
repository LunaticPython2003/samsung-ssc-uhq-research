import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;

/**
 * Search vendor A2DP stack for direct references to Samsung SSC debug strings.
 * Prints selected caller decompilations, bounded to avoid huge logs.
 */
public class InspectSscCalls extends GhidraScript {
    public void run() throws Exception {
        String[] keys = {
            "a2dp_vendor_ssc_encoder",
            "a2dp_ssc_encode_frames",
            "A2DP_VendorLoadEncoderSsc",
            "A2DP_BuildInfoSsc",
            "A2DP_ParseInfoSsc",
            "ssc_encoder_create",
            "SSC output_pos",
            "SscVendorGetTrackBitrateLimitation",
            "SscVendorGetTrackSampleRate",
            "a2dp_vendor_ssc_send_frames",
            "a2dp_vendor_ssc_encoder_update",
            "uhq ver2"
        };
        Memory memory=currentProgram.getMemory();
        ReferenceManager refs=currentProgram.getReferenceManager();
        DecompInterface decomp=new DecompInterface();
        decomp.openProgram(currentProgram);
        HashSet<Address> done=new HashSet<>();
        int count=0;
        for(String key:keys) {
            println("\n#### NEEDLE "+key+" ####");
            byte[] bytes=key.getBytes(StandardCharsets.US_ASCII);
            Address start=memory.getMinAddress();
            for(int matches=0; matches<20 && start!=null; matches++) {
                Address hit=memory.findBytes(start,bytes,null,true,monitor);
                if(hit==null)break;
                println("MATCH: "+hit);
                int refcount=0;
                for(Reference ref:refs.getReferencesTo(hit)) {
                    refcount++;
                    Function f=currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                    println("REF: "+ref.getFromAddress()+" function="+
                        (f==null?"none":f.getName()+"@"+f.getEntryPoint()));
                    if(f!=null&&!done.contains(f.getEntryPoint())&&count<24) {
                        done.add(f.getEntryPoint());count++;
                        DecompileResults d=decomp.decompileFunction(f,90,monitor);
                        if(d!=null&&d.decompileCompleted()&&d.getDecompiledFunction()!=null) {
                            String code=d.getDecompiledFunction().getC();
                            println("DECOMPILED "+f.getName()+"\n"+
                                code.substring(0,Math.min(code.length(),14000)));
                        }
                    }
                }
                println("REFERENCE COUNT "+refcount);
                try {start=hit.add(1);} catch(Exception e) {break;}
            }
        }
        decomp.dispose();
        println("DECOMPILATION COUNT "+count);
    }
}
