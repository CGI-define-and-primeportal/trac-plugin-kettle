$(document).ready(function() {
  // setting global variable so we can access later in local scope
  var transformation_id,
      transform_name,
      transform_wrapper,
      execute_btn_handler,
      group_label,
      timeout_browser;

  $("#content").find("h2").addAnchor(_("Link to this section"));

  $('.toggle-parameters-form').click(function(e) {
    $("i", this).toggleClass("icon-resize-full icon-resize-small");
    $(this).parent().parent().find('.parameters-form').toggle('slow');
  });

  var executions = 0;
  var executions_loading = false;
  function loadExecutions(specific_elem) {
    executions ++;
    executions_loading = true;
    var results_tables = specific_elem ? $("table", specific_elem) : $(".results-table");
    $(results_tables).each(function(i) {
      var table = $(this);
      var result_url = table.attr("data-url") + "?_=" + (new Date().getTime());
      // Load table's contents from URL
      $.ajax({
        url: result_url,
        success: function(data) {
          // Put results in DOM (hidden)
          var updated_contents = $("#ajax-results").html(data);
          // Check revision numbers against one another, update if different
          if($("td.rev", updated_contents).html() != $("td.rev", table).html()) {
            $("tbody", table).html(updated_contents.html());
            if(executions != 1) {
              $("tbody tr td", table).effect({
                duration: 2000,
                effect: "highlight",
                color: "#DFEEFD"
              });
            }
            $("tr td:first-child", table).remove();
            // If we've specified a transform object, clear the timeout and set success status
            if(specific_elem) {
              clearTimeout(specific_elem.data("timeout"));
              specific_elem.data("n", 0);
              $(".execute-actions .btn", specific_elem).removeClass("disabled");
              $(".execute-actions .btn:first", specific_elem).html("<i class='icon-bolt'></i> Execute transformation");
            }

            // stop sending requests to find new revision numbers
            clearInterval(timeout_browser);
            timeout_browser = 0;
          }
          if((i + 1) == results_tables.length) executions_loading = false;
        },
        error: function() {
          if((i + 1) == results_tables.length) executions_loading = false;
        }
      });
    });
  };

  // needed to load the initial inline browser links
  loadExecutions();

  $("#bi-integration-url-dialog").dialog({autoOpen:false,width:500, modal:true, title:"Report GET URL"});
  $("#content .get-url-btn").click(function(){
    example_url = this.href + "&" + $(this).parent().parent().find("input.bi-parameter").serialize();
    $("#bi-integration-url-placeholder").attr('href', example_url);
    $("#bi-integration-url-placeholder").text(example_url);
    $("#bi-integration-url-dialog").dialog('open');
    return false;
  });

  $("#dialogupload").dialog({autoOpen:false, width:400, modal:true, title:"Upload Transformations"});
  $("#uploadbutton").click(function(){
    $("#dialogupload").dialog('open');
    return false;
  });
  $("#dialogschedule").dialog({autoOpen:false, width:400, modal:true, title:"Schedule Transformations"});
  $("#schedulebutton").click(function(){
    $("#dialogschedule").dialog('open');
    return false;
  });

  // Execution event
  $(".execute-actions a[data-action]").click(function() {
    transform_name = $(this).closest(".execute-actions").attr("data-transform");
    transform_wrapper = $("#transform-" + transform_name);
    execute_btn_handler = $(".execute-actions", transform_wrapper);
    group_label = $(".group-label", execute_btn_handler);

    if($(".btn.disabled", execute_btn_handler).length == 0) {
      // Set our form values given the execution request
      $("#exec-action").val($(this).attr("data-action"));
      $("#exec-transform").val(transform_name);
      $("#exec-form input.bi-parameter").remove();
      transform_wrapper.find("input.bi-parameter").clone().appendTo($("#exec-form"));
      // Change the button state to loading
      group_label.html("<i class='icon-spin icon-spinner'></i> Executing transformation");
      group_label.removeClass("btn-success").addClass("btn-warning");
      group_label.next().removeClass("btn-success").addClass("btn-warning");
      $(".btn", execute_btn_handler).addClass("disabled");

      // If our request is not to async
      if($("#exec-action").val() != "execute_download") {
        $("#exec-form").ajaxSubmit({
          url: $("#exec-form").attr("action"),
          success: function(data) {
            showProgress(data, group_label);
          },
          error: function() {
            // TODO something better than a alert box
            alert("Unable to execute transformation.")
          }
        });
      }
      else {
        // we have this set at an arbitary 30 seconds - maybe we can 
        // be cleverer than that? why don't we request via $.ajax() and send 
        // a response so we know for sure when to change the icons back?
        setTimeout(function() {
          $(".btn", execute_btn_handler).removeClass("disabled");
          group_label.removeClass("disabled").addClass("btn-success").html("<i class='icon-bolt'></i> Execute transformation");
          group_label.next().addClass("btn-success");
        }, 30000);
        $("#exec-form").submit();
      }
    }
    execute_btn_handler.removeClass("open");
    return false;
  });

  function showProgress(data) {
    /**
    Set up for a series of XMLHttpRequests for data. We use setInterval() 
    to repeat requests by calling the checkTransformProgress() function.

    This is set to an arbitary length of 2 seconds, which seems like a good 
    compromise between being responsive to the user, and not tieing up too 
    many apache threads. 
    **/

    transform_id = data['transform_id'];
    var progressHandler = setInterval(function(){checkTransformProgress(transform_id)}, 2000)

    function updateUserInterface(timeoutHandler, btn, alert, message) {
      /**
      Update the UI to reflect the completion or failure of a transformation, 
      and expire the setInterval progressHandler to stop sending any more requests.
      **/

      // expire setInterval()
      clearInterval(timeoutHandler);
      progressHandler = 0;

      // update the UI (change button styling, add a alert message)
      group_label.removeClass("btn-warning disabled").addClass(btn).html("<i class='icon-bolt'></i> Execute transformation");
      group_label.next().removeClass("btn-warning").addClass(btn);
      $("#content").prepend('<div class="cf alert ' + alert + ' alert-dismissable individual">\
                              <i class="alert-icon icon-info-sign"></i>\
                              <div style="display:inline">' + message + '</div>\
                              <button type="button" class="close btn btn-mini" data-dismiss="alert">\
                                <i class="icon-remove"></i>\
                              </button>\
                            </div>')
    }

    function checkTransformProgress(uuid) {
      /**
      Sends a AJAX request to the server, with the uuid for the transformation 
      as the data packet via JSON. This then invokes a DB query via the Python 
      DB API, which checks on the progress of our transformation.

      If we recieve a successful response, we check the status - which we 
      expect to be null, running, success or error. Based on this value we
      update the user interface appropriately.
      **/
      $.ajax({
        type: 'GET',
        data: {'uuid': uuid},
        url: window.tracBaseUrl + 'ajax/businessintelligence',
        success: function(data) {
          $execute_button = $("a[data-action=execute_async]")
          // use jQuery inArray as JS indexOf only supported in IE 8+
          if ($.inArray(data['status'], ['running', null]) >=0) {
            $execute_button.removeClass("btn-success").addClass("btn-warning");
          }
          else if (data['status'] == "success") {
            updateUserInterface(progressHandler, 'btn-success', 'alert-success',
              "Successfully executed '" + transform_name + "' transformation.")
            // now we also update the inline file browser div
            timeout_browser = setInterval(function() { if(!executions_loading) loadExecutions(); }, 2000);
          }
          else if (data['status'] == 'error') {
            updateUserInterface(progressHandler, 'btn-danger', 'alert-danger',
              "Failed to execute '" + transform_name + "' transformation.")
          }
        }
      });
    }
  }

});