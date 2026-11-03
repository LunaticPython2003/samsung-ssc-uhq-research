import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.address.Address;
import java.util.Arrays;

public class TraceSscApi extends GhidraScript {
    public void run() throws Exception {
        Memory memory=currentProgram.getMemory();
        for(String value:new String[]{"0020abb8","0020abc0","00fabbe8"}) {
            Address a=toAddr(value);
            byte[] out=new byte[32];
            try {
                int n=memory.getBytes(a,out);
                StringBuilder b=new StringBuilder();
                for(int i=0;i<n;i++) b.append(String.format("%02x ",out[i]&0xff));
                println("DATA_AT "+a+" "+b.toString());
            } catch(Exception e) {println("DATA_ERR "+a+" "+e.getMessage());}
        }
        DecompInterface decomp=new DecompInterface();
        decomp.openProgram(currentProgram);
        FunctionIterator it=currentProgram.getFunctionManager().getFunctions(true);
        int count=0;
        for(Function f:it) {
            String name=f.getName();
            boolean isSsc=name.contains("Ssc") || name.contains("ssc");
            if(!isSsc || f.isThunk()) continue;
            println("FOUND "+name+" @ "+f.getEntryPoint());
            boolean target=
                name.contains("BuildInfoSsc") ||
                name.contains("GetTrackSampleRateSsc") ||
                name.contains("GetTrackBitsPerSampleSsc") ||
                name.contains("GetTrackChannelCountSsc") ||
                name.contains("GetMediaPayloadHeaderSsc") ||
                name.contains("GetPacketTimestampSsc") ||
                name.contains("GetFrameSizeSsc") ||
                name.contains("BuildCodecHeaderSsc") ||
                name.contains("GetCodecHeaderSsc") ||
                name.contains("GetTrackBitRateSsc") ||
                name.contains("A2DP_VendorGetBitRateSsc") ||
                name.contains("A2DP_VendorGetBitrateSsc");
            if(target && count<18) {
                count++;
                DecompileResults r=decomp.decompileFunction(f,35,monitor);
                if(r!=null && r.decompileCompleted() && r.getDecompiledFunction()!=null)
                    println("CODE_BEGIN "+name+"\n"+r.getDecompiledFunction().getC()+"\nCODE_END "+name);
                else
                    println("CODE_ERR "+name+" "+(r!=null?r.getErrorMessage():"null"));
            }
        }
        println("DECOMPILED "+count);
        decomp.dispose();
    }
}
