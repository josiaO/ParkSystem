/* Print decompiler output for the small set of fresh-audit functions that
 * define the video, frame, region, and callback contract. */
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;

public class FreshOcxDecompile extends GhidraScript {
    @Override
    public void run() throws Exception {
        String program = currentProgram.getName();
        String[] names;
        if (program.equals("NetSDK.dll")) {
            names = new String[] {"Net_StartVideo", "Net_StopVideo", "Net_AddPlayWindow",
                "Net_GetJpgBuffer", "Net_GetFrameData", "Net_SetDrawFunCallBack",
                "Net_ShowPlateRegion", "Net_RegImageRecvEx2", "Net_RegReportMessEx",
                "Net_QueryVideoDetectSetup"};
        }
        else if (program.equals("PlaySdk.dll")) {
            names = new String[] {"Play_Init", "Play_AddCamera", "Play_OpenCamera",
                "Play_AddPlayWindow", "Play_GetJpgBuffer", "Play_GetFrameData",
                "Play_SetDrawFunCallBack", "Play_ShowPlateRegion", "Play_CloseCamera"};
        }
        else if (program.equals("RtspRecvSdk.dll")) {
            names = new String[] {"Rtsp_Init", "Rtsp_AddCamera", "Rtsp_StartVideo",
                "Rtsp_StopVideo", "Rtsp_QueryVideoState", "Rtsp_GetVideoFrame",
                "FUN_10004360", "FUN_100042d0", "FUN_10003d30", "FUN_10004e90"};
        }
        else if (program.equals("DecodeSdk.dll")) {
            names = new String[] {"Decode_StreamOpenEx", "Decode_StreamPlayEx",
                "Decode_StreamStopEx", "Decode_StreamCloseEx", "Decode_AddDataEx",
                "Decode_GetJpgBuffer", "Decode_GetFrameData", "Decode_ShowPlateRegion",
                "Decode_SetDrawFunCallBack"};
        }
        else {
            names = new String[0];
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        for (String name : names) {
            Function function = findFunction(name);
            if (function == null) {
                println("MISSING_FUNCTION " + name);
                continue;
            }
            DecompileResults result = decompiler.decompileFunction(function, 120, monitor);
            println("=== DECOMPILE " + program + " " + function.getEntryPoint() + " " + name + " ===");
            if (result.getDecompiledFunction() == null) {
                println("DECOMPILE_ERROR " + result.getErrorMessage());
            }
            else {
                println(result.getDecompiledFunction().getC());
            }
        }
        decompiler.dispose();
    }

    private Function findFunction(String name) {
        for (Function function : currentProgram.getFunctionManager().getFunctions(true)) {
            if (function.getName().equals(name)) {
                return function;
            }
        }
        return null;
    }
}
