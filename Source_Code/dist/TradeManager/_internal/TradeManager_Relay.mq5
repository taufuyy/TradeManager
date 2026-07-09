//+------------------------------------------------------------------+
//|                                             TradeManager_Relay.mq5|
//|                                     Copyright 2026, TradeManager |
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "TradeManager"
#property link      ""
#property version   "1.00"
#property strict

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   // Timer set to 50 milliseconds for lightning fast execution
   EventSetMillisecondTimer(50);
   Print("TradeManager Relay EA Started. Listening for Python commands...");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   Print("TradeManager Relay EA Stopped.");
  }

//+------------------------------------------------------------------+
//| Timer function                                                   |
//+------------------------------------------------------------------+
void OnTimer()
  {
   string file_name;
   long search_handle = FileFindFirst("tm_cmd_*.txt", file_name);
   
   if(search_handle != INVALID_HANDLE)
     {
      do
        {
         ProcessCommandFile(file_name);
        }
      while(FileFindNext(search_handle, file_name));
      
      FileFindClose(search_handle);
     }
  }

//+------------------------------------------------------------------+
//| Process Command File                                             |
//+------------------------------------------------------------------+
void ProcessCommandFile(string filename)
  {
   int file_handle = FileOpen(filename, FILE_READ|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE);
   if(file_handle != INVALID_HANDLE)
     {
      string command_str = FileReadString(file_handle);
      FileClose(file_handle);
      
      // Delete the file immediately to acknowledge receipt and prevent double execution
      FileDelete(filename);
      
      Print("Received command: ", command_str);
      ExecuteCommand(command_str);
     }
  }

//+------------------------------------------------------------------+
//| Execute Command                                                  |
//+------------------------------------------------------------------+
void ExecuteCommand(string cmd_str)
  {
   string parts[];
   int count = StringSplit(cmd_str, '|', parts);
   
   if(count >= 3)
     {
      string action = parts[0];
      string symbol = parts[1];
      long magic = StringToInteger(parts[2]);
      
      if(action == "CLOSE_ALL")
        {
         CloseAllPositions(symbol, magic);
        }
      else if(action == "CLOSE_TICKETS" && count >= 4)
        {
         string tickets_str = parts[3];
         CloseSpecificPositions(symbol, magic, tickets_str);
        }
      else if(action == "BULK_SLTP" && count >= 4)
        {
         string sltp_str = parts[3];
         ApplyBulkSLTP(symbol, magic, sltp_str);
        }
     }
  }

//+------------------------------------------------------------------+
//| Apply Bulk SL/TP                                                 |
//+------------------------------------------------------------------+
void ApplyBulkSLTP(string target_symbol, long target_magic, string sltp_str)
  {
   string pairs[];
   int count = StringSplit(sltp_str, ',', pairs);
   
   for(int i=0; i<count; i++)
     {
      string item = pairs[i];
      if(StringLen(item) == 0) continue;
      
      string fields[];
      int fcount = StringSplit(item, ':', fields);
      if(fcount >= 3)
        {
         ulong ticket = StringToInteger(fields[0]);
         double sl = StringToDouble(fields[1]);
         double tp = StringToDouble(fields[2]);
         
         if(PositionSelectByTicket(ticket))
           {
            string sym = PositionGetString(POSITION_SYMBOL);
            long mag = PositionGetInteger(POSITION_MAGIC);
            if(sym == target_symbol && (target_magic == 0 || mag == target_magic))
              {
               MqlTradeRequest request;
               MqlTradeResult result;
               ZeroMemory(request);
               ZeroMemory(result);
               
               request.action = TRADE_ACTION_SLTP;
               request.position = ticket;
               request.symbol = sym;
               request.sl = sl;
               request.tp = tp;
               
               bool res = OrderSendAsync(request, result);
               if(!res) Print("BULK_SLTP OrderSendAsync failed, error: ", GetLastError());
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Close All Positions (Async)                                      |
//+------------------------------------------------------------------+
void CloseAllPositions(string target_symbol, long target_magic)
  {
   int total = PositionsTotal();
   int sent_count = 0;
   
   // We loop backwards
   for(int i = total - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
        {
         string sym = PositionGetString(POSITION_SYMBOL);
         long mag = PositionGetInteger(POSITION_MAGIC);
         
         // If magic == 0, we close regardless of magic to match python's magic=0 logic
         if(sym == target_symbol && (target_magic == 0 || mag == target_magic))
           {
            double vol = PositionGetDouble(POSITION_VOLUME);
            long type = PositionGetInteger(POSITION_TYPE);
            
            MqlTradeRequest request;
            MqlTradeResult result;
            ZeroMemory(request);
            ZeroMemory(result);
            
            request.action = TRADE_ACTION_DEAL;
            request.position = ticket;
            request.symbol = sym;
            request.volume = vol;
            request.deviation = 50; // allow 50 points deviation
            request.magic = target_magic;
            
            // Determine Filling Mode
            int filling = (int)SymbolInfoInteger(sym, SYMBOL_FILLING_MODE);
            if((filling & SYMBOL_FILLING_FOK) != 0)
               request.type_filling = ORDER_FILLING_FOK;
            else if((filling & SYMBOL_FILLING_IOC) != 0)
               request.type_filling = ORDER_FILLING_IOC;
            else
               request.type_filling = ORDER_FILLING_RETURN;
            
            if(type == POSITION_TYPE_BUY)
              {
               request.type = ORDER_TYPE_SELL;
               request.price = SymbolInfoDouble(sym, SYMBOL_BID);
              }
            else
              {
               request.type = ORDER_TYPE_BUY;
               request.price = SymbolInfoDouble(sym, SYMBOL_ASK);
              }
              
            // Fire asynchronously! This is the magic that makes it instant.
            if(OrderSendAsync(request, result))
              {
               sent_count++;
              }
            else
              {
               Print("OrderSendAsync failed for ticket ", ticket, " Error: ", GetLastError());
              }
           }
        }
     }
     
   Print("Successfully fired OrderSendAsync for ", sent_count, " positions.");
  }

//+------------------------------------------------------------------+
//| Close Specific Positions (Async)                                 |
//+------------------------------------------------------------------+
void CloseSpecificPositions(string target_symbol, long target_magic, string tickets_str)
  {
   string tickets_arr[];
   int t_count = StringSplit(tickets_str, ',', tickets_arr);
   int sent_count = 0;
   
   for(int i = 0; i < t_count; i++)
     {
      ulong target_ticket = StringToInteger(tickets_arr[i]);
      if(target_ticket > 0 && PositionSelectByTicket(target_ticket))
        {
         string sym = PositionGetString(POSITION_SYMBOL);
         long mag = PositionGetInteger(POSITION_MAGIC);
         
         if(sym == target_symbol && (target_magic == 0 || mag == target_magic))
           {
            double vol = PositionGetDouble(POSITION_VOLUME);
            long type = PositionGetInteger(POSITION_TYPE);
            
            MqlTradeRequest request;
            MqlTradeResult result;
            ZeroMemory(request);
            ZeroMemory(result);
            
            request.action = TRADE_ACTION_DEAL;
            request.position = target_ticket;
            request.symbol = sym;
            request.volume = vol;
            request.deviation = 50;
            request.magic = target_magic;
            
            int filling = (int)SymbolInfoInteger(sym, SYMBOL_FILLING_MODE);
            if((filling & SYMBOL_FILLING_FOK) != 0)
               request.type_filling = ORDER_FILLING_FOK;
            else if((filling & SYMBOL_FILLING_IOC) != 0)
               request.type_filling = ORDER_FILLING_IOC;
            else
               request.type_filling = ORDER_FILLING_RETURN;
            
            if(type == POSITION_TYPE_BUY)
              {
               request.type = ORDER_TYPE_SELL;
               request.price = SymbolInfoDouble(sym, SYMBOL_BID);
              }
            else
              {
               request.type = ORDER_TYPE_BUY;
               request.price = SymbolInfoDouble(sym, SYMBOL_ASK);
              }
              
            if(OrderSendAsync(request, result))
              {
               sent_count++;
              }
            else
              {
               Print("OrderSendAsync failed for ticket ", target_ticket, " Error: ", GetLastError());
              }
           }
        }
     }
   Print("Successfully fired OrderSendAsync for ", sent_count, " specific positions.");
  }
//+------------------------------------------------------------------+

